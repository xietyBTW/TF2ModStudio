/*
 * Снимок модели для обложки: кадр вне экрана, камера своя, фон прозрачный
 *
 * Экран не трогаем: снимок рисуется в отдельный буфер и не зависит от того,
 * как человек повернул модель. Камера ортографическая и смотрит чуть сбоку и
 * сверху, как на иконках рюкзака: в перспективе длинное оружие выходило бы
 * клином.
 *
 * Буфер float: при рендере в буфер three.js отдаёт линейный цвет, и в 8 битах
 * тёмные тона пошли бы полосами. В sRGB переводим сами при выгрузке
 */

import { itemPose } from './viewer_item_pose.js';

//: Сколько сцена должна простоять без перемен, прежде чем снимать
const QUIET_MS = 1000;
//: Дольше не ждём: модель так и не пришла или не оделась
const GIVE_UP_MS = 20000;

/**
 * window.snapshotWhenSettled для вьювера: обещание PNG base64 или null
 *
 * Когда снимать. Модель должна быть в кадре и одета, а текстуры приезжают
 * отдельно от OBJ и не разом. Поэтому ждём, пока у загрузчиков three.js
 * ничего нет в пути и секунду ничего не менялось. Снимается первая модель,
 * пришедшая после вызова: если её сменили раньше, снимок отменяется - чужая
 * модель на обложке хуже никакой
 *
 * model() - модель в кадре, keep(mesh) - что снимать, plain() - в кадре
 * обычная модель предмета, а не особая сцена
 */
export function snapshotWaiter(THREE, renderer, scene, model, keep, plain) {
  // Через этот менеджер идут все загрузчики вьювера: OBJ, текстуры, кадры гифок
  const manager = THREE.DefaultLoadingManager;
  let loading = false;
  let touched = 0;
  const touch = () => { touched = performance.now(); };
  manager.onStart = () => { loading = true; touch(); };
  manager.onProgress = touch;
  manager.onLoad = () => { loading = false; touch(); };

  const hasMap = (root) => {
    let found = false;
    root.traverse((o) => { if (o.isMesh && o.material && o.material.map) found = true; });
    return found;
  };

  // fresh - ждать новую модель (её сейчас грузят), иначе снимать ту, что в
  // кадре. follow - модель сменилась (восстановилась своя модель работы),
  // снимать новую, а не отменять: за тем, тот ли это предмет, следит хозяин
  // снимка. lay - значение или функция: шапка это или оружие, бывает ясно
  // только после загрузки
  return ({ lay = false, fresh = true, follow = false } = {}) => new Promise((resolve) => {
    const started = performance.now();
    const before = fresh ? model() : null;
    let target = null;
    const check = () => {
      const now = performance.now();
      if (now - started > GIVE_UP_MS) { resolve(null); return; }
      const current = model();
      if (current && current !== before && current !== target && (!target || follow)) {
        target = current;
        touch();
      }
      if (target && current !== target) { resolve(null); return; }
      const ready = target && plain() && !loading && now - touched >= QUIET_MS
        && hasMap(target);
      if (!ready) { setTimeout(check, 250); return; }
      try {
        const flat = typeof lay === 'function' ? lay() : lay;
        resolve(snapshotModel(THREE, renderer, scene, target, { keep, lay: flat }));
      } catch (err) {
        console.warn('[3D viewer] snapshot failed:', err);
        resolve(null);
      }
    };
    check();
  });
}

//: Откуда смотрит камера на шапку: немного сбоку и сверху от вида вьювера
const VIEW_DIR = [0.35, 0.28, 1];
//: Насколько сверху смотрим на оружие: чуть видна верхняя грань, как в рюкзаке
const TILT = 0.3;
//: Куда смотрит оружие во вьювере: c_models висят на кости руки. Замерено на
//: стоковых обрезе, ракетомёте, ноже и снайперке: ствол и остриё в +Y, прицел
//: снайперки в -Z
const HAND_FRAME = { forward: [0, 1, 0], up: [0, 0, -1] };
//: Оси уже положенной модели: ствол влево, верх вверх, бок к зрителю
const LAID = { right: [1, 0, 0], up: [0, 1, 0], back: [0, 0, 1] };
//: Сколько вершин хватает, чтобы понять форму и рамку
const MAX_POINTS = 40000;
//: Поле вокруг модели, доля размера
const MARGIN = 0.06;

/**
 * PNG модели base64 без префикса, null - снимать нечего
 *
 * keep(mesh) отсекает то, чего на обложке быть не должно (призрак оригинала).
 * Всё в сцене, кроме root и света, на время снимка прячется: подложка сцены
 * (тело персонажа, скайбокс) обложке не нужна.
 * lay - положить длинную модель набок, стволом влево, как оружие в рюкзаке.
 * Шапке не годится: высокая шапка должна стоять
 */
export function snapshotModel(THREE, renderer, scene, root,
                              { size = 512, keep = () => true, lay = false } = {}) {
  root.updateMatrixWorld(true);
  const points = _worldPoints(THREE, root, keep);
  if (!points.length) return null;

  // Вьювер уже положил оружие (viewer_lay.js) - его оси и есть оси кадра:
  // подсказка руки к повёрнутой модели не подходит, а обложка совпадёт с экраном
  const pose = !lay ? null : root.userData.laid ? LAID : itemPose(points, HAND_FRAME);
  const camera = _fitCamera(THREE, points, pose);
  const restore = _isolate(THREE, renderer, scene, root, keep);
  const target = new THREE.WebGLRenderTarget(size, size, {
    type: THREE.FloatType, samples: 4,
  });
  const pixels = new Float32Array(size * size * 4);
  try {
    renderer.setRenderTarget(target);
    renderer.clear();
    renderer.render(scene, camera);
    renderer.readRenderTargetPixels(target, 0, 0, size, size, pixels);
  } finally {
    renderer.setRenderTarget(null);
    target.dispose();
    restore();
  }
  return _toPng(pixels, size);
}

/** Вершины видимых мешей в мировых координатах, не больше MAX_POINTS */
function _worldPoints(THREE, root, keep) {
  const meshes = [];
  root.traverseVisible((o) => {
    if (o.isMesh && keep(o) && o.geometry?.attributes?.position) meshes.push(o);
  });
  const total = meshes.reduce((n, m) => n + m.geometry.attributes.position.count, 0);
  const step = Math.max(1, Math.ceil(total / MAX_POINTS));
  const out = [];
  const p = new THREE.Vector3();
  for (const mesh of meshes) {
    const pos = mesh.geometry.attributes.position;
    for (let i = 0; i < pos.count; i += step) {
      p.fromBufferAttribute(pos, i).applyMatrix4(mesh.matrixWorld);
      out.push(p.x, p.y, p.z);
    }
  }
  return out;
}

/**
 * Ортокамера, в которую модель входит целиком и по центру
 *
 * pose - оси оружия (viewer_item_pose.js): смотрим в его бок чуть сверху.
 * Без неё - вид вьювера по умолчанию, шапка стоит как стоит
 */
function _fitCamera(THREE, points, pose) {
  const box = new THREE.Box3().setFromArray(points);
  const center = box.getCenter(new THREE.Vector3());
  const radius = box.getSize(new THREE.Vector3()).length() / 2 || 1;
  const camera = new THREE.OrthographicCamera(-1, 1, 1, -1, 0.01, 1);
  const dir = pose
    ? new THREE.Vector3(...pose.back).addScaledVector(new THREE.Vector3(...pose.up), TILT)
    : new THREE.Vector3(...VIEW_DIR);
  if (pose) camera.up.set(...pose.up);
  camera.position.copy(center).addScaledVector(dir.normalize(), radius * 4);
  camera.lookAt(center);
  camera.updateMatrixWorld(true);

  // Рамка по самим вершинам в осях камеры: по сфере или коробке длинное
  // оружие наискось вышло бы мелким
  const inv = camera.matrixWorldInverse;
  const lo = new THREE.Vector3(Infinity, Infinity, Infinity);
  const hi = new THREE.Vector3(-Infinity, -Infinity, -Infinity);
  const p = new THREE.Vector3();
  for (let i = 0; i < points.length; i += 3) {
    p.set(points[i], points[i + 1], points[i + 2]).applyMatrix4(inv);
    lo.min(p);
    hi.max(p);
  }
  const half = Math.max(hi.x - lo.x, hi.y - lo.y) / 2 * (1 + 2 * MARGIN);
  const cx = (lo.x + hi.x) / 2;
  const cy = (lo.y + hi.y) / 2;
  Object.assign(camera, {
    left: cx - half, right: cx + half, top: cy + half, bottom: cy - half,
    // Камера смотрит в -Z: ближнее - это наибольший z
    near: Math.max(0.001, -hi.z - radius * 0.1), far: -lo.z + radius * 0.1,
  });
  camera.updateProjectionMatrix();
  return camera;
}

/** Прячет всё, кроме модели и света, и делает фон прозрачным. Возвращает отмену */
function _isolate(THREE, renderer, scene, root, keep) {
  const hidden = [];
  const hide = (o) => { if (o.visible) { o.visible = false; hidden.push(o); } };
  for (const child of scene.children) {
    if (child !== root && !child.isLight) hide(child);
  }
  root.traverse((o) => { if (o.isMesh && !keep(o)) hide(o); });

  const background = scene.background;
  const clear = renderer.getClearColor(new THREE.Color());
  const alpha = renderer.getClearAlpha();
  scene.background = null;
  renderer.setClearColor(0x000000, 0);
  return () => {
    for (const o of hidden) o.visible = true;
    scene.background = background;
    renderer.setClearColor(clear, alpha);
  };
}

/** Линейный float снизу вверх -> PNG sRGB сверху вниз */
function _toPng(pixels, size) {
  const canvas = document.createElement('canvas');
  canvas.width = canvas.height = size;
  const ctx = canvas.getContext('2d');
  const image = ctx.createImageData(size, size);
  const out = image.data;
  let any = false;
  for (let y = 0; y < size; y++) {
    const src = (size - 1 - y) * size * 4;
    const dst = y * size * 4;
    for (let x = 0; x < size * 4; x += 4) {
      const a = pixels[src + x + 3];
      if (a <= 0) continue;                 // прозрачный пиксель остаётся нулём
      any = true;
      // Прозрачность сцены смешана с чёрным фоном: цвет делим обратно на неё
      for (let c = 0; c < 3; c++) {
        out[dst + x + c] = _srgbByte(pixels[src + x + c] / Math.min(1, a));
      }
      out[dst + x + 3] = Math.round(Math.min(1, a) * 255);
    }
  }
  if (!any) return null;
  ctx.putImageData(image, 0, 0);
  return canvas.toDataURL('image/png').split(',')[1];
}

function _srgbByte(linear) {
  const v = Math.min(1, Math.max(0, linear));
  const s = v <= 0.0031308 ? v * 12.92 : 1.055 * Math.pow(v, 1 / 2.4) - 0.055;
  return Math.round(s * 255);
}
