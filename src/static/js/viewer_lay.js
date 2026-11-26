/*
 * Кладёт оружие в кадре ровно: ствол влево, верх вверх, бок к зрителю
 *
 * Стороны подсказывает Python (src/services/item_pose_hint.py: камера иконки
 * рюкзака из модели или кость руки), оси берёт форма (viewer_item_pose.js).
 * Поворачивается сама модель, а не камера: орбита вращает вокруг мировой
 * вертикали, и с повёрнутой камерой предмет кувыркался бы при осмотре
 *
 * После поворота прежние габариты из Python не годятся: коробка повёрнутой
 * модели другая. Центр и масштаб считаются заново той же меркой
 * (domain/preview/obj_bounds.py: наибольшая сторона - TARGET_EXTENT)
 */

import { itemPose } from './viewer_item_pose.js';

const TARGET_EXTENT = 2.0;
//: Сколько вершин хватает, чтобы понять форму (как у снимка обложки)
const MAX_POINTS = 40000;

/**
 * Поворачивает object по подсказке hint {forward, up[, view]}
 *
 * Возвращает габариты для кадра {cx, cy, cz, scale}: новые, если модель
 * положена, иначе bounds из Python как есть. object.userData.laid говорит
 * снимку обложки, что оси кадра уже оси оружия (viewer_snapshot.js)
 *
 * ghost(mesh) - призрак оригинала рядом со своей моделью. Есть он - поза и
 * габариты по нему одному: своя модель до подгонки бывает в метрах и в
 * стороне (так же считает Python, domain/preview/obj_bounds.py)
 */
export function layItem(THREE, object, hint, bounds, ghost = () => false) {
  object.userData.laid = false;
  if (!hint) return bounds;
  object.position.set(0, 0, 0);
  object.scale.setScalar(1);
  object.quaternion.identity();
  object.updateMatrixWorld(true);

  const points = _points(THREE, object, ghost);
  const pose = points.length ? itemPose(points, hint) : null;
  if (!pose) return bounds;

  const basis = new THREE.Matrix4().makeBasis(
    new THREE.Vector3(...pose.right), new THREE.Vector3(...pose.up),
    new THREE.Vector3(...pose.back));
  // makeBasis переводит оси кадра в оси модели, нам нужно обратное
  object.quaternion.setFromRotationMatrix(basis.transpose());
  object.userData.laid = true;
  return _bounds(points, pose);
}

function _points(THREE, object, ghost) {
  let meshes = [];
  object.traverse((o) => { if (o.isMesh && o.geometry?.attributes?.position) meshes.push(o); });
  if (meshes.some(ghost)) meshes = meshes.filter(ghost);
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

function _bounds(points, { right, up, back }) {
  const lo = [Infinity, Infinity, Infinity];
  const hi = [-Infinity, -Infinity, -Infinity];
  const axes = [right, up, back];
  for (let i = 0; i + 2 < points.length; i += 3) {
    for (let k = 0; k < 3; k++) {
      const a = axes[k];
      const v = points[i] * a[0] + points[i + 1] * a[1] + points[i + 2] * a[2];
      if (v < lo[k]) lo[k] = v;
      if (v > hi[k]) hi[k] = v;
    }
  }
  const extent = Math.max(hi[0] - lo[0], hi[1] - lo[1], hi[2] - lo[2]);
  return {
    cx: (lo[0] + hi[0]) / 2, cy: (lo[1] + hi[1]) / 2, cz: (lo[2] + hi[2]) / 2,
    scale: extent > 0 ? TARGET_EXTENT / extent : 1,
  };
}
