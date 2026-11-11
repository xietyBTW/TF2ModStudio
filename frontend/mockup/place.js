/*
 * Посадка картинки на часть: размер, поворот, место. Без неё картинка
 * растягивалась бы по прямоугольнику части, теряя пропорции
 *
 * Окно показывает НАСТОЯЩУЮ развёртку части (треугольники, по которым
 * маскирует склейка), а не рамку: положенное вне маски при сборке исчезает, и
 * рамка обещала бы то, чего не будет
 *
 * Холст и расчёт посадки - в place-draw.js, колонка слоёв - в place-layers.js
 */

import * as api from './api.js';
import { loadImage } from './util.js';
import { applyView } from './preview.js';
import { chooseFile } from './util.js';
import { hintParts, refreshParts } from './parts.js';
import { P } from './parts-state.js';
import { showLayers } from './place-layers.js';
import { HANDLE_GAP, HANDLE_R, boxOf, drawPlace, gripAt, localPoint, placeRect, placeView,
         resizeBy, shownImage } from './place-draw.js';
import { t } from './i18n.js';

const placeDlg = document.getElementById('placedlg');

/**
 * Скопированная картинка части: файл и посадка с размером В ДОЛЯХ ТЕКСТУРЫ
 *
 * Именно так, а не масштабом: масштаб считается от габарита части, и тот же
 * масштаб на другой детали дал бы другой размер. Python пересчитывает
 * `size_uv` в масштаб новой части (PartsEditor._absolute_size).
 */
let clip = null;

/** Есть ли что вставить: Ctrl+V над деталью на модели смотрит сюда */
export const imageClip = () => clip;

function remember(value) {
  clip = value;
}

/** Вставляет скопированную картинку на часть - новым слоем поверх */
export async function pasteImageTo(part) {
  if (!clip) return false;
  return persist(part, clip.path, clip.options, null);
}

/** Запись слоя для окна: копия, чтобы правки до «Готово» не трогали ответ */
function layerSpec(raw) {
  return { ...raw,
           scale_y: raw.scale_y === undefined ? raw.scale : raw.scale_y,
           offset: [raw.offset[0], raw.offset[1]],
           flip_x: !!raw.flip_x, flip_y: !!raw.flip_y };
}

const freshSpec = (path) => ({ path, fit: 'contain', angle: 0, scale: 1, scale_y: 1,
                               offset: [0, 0], flip_x: false, flip_y: false });

/**
 * Посадка скопированной картинки: размер В ДОЛЯХ ТЕКСТУРЫ -> масштаб части
 *
 * Тот же расчёт, что `part_images.absolute_size`: холст в пропорциях
 * текстуры, поэтому доля холста и доля текстуры - одно и то же
 */
function specFromClip(c, image, box, W, H) {
  const spec = { ...freshSpec(c.path), fit: c.options.fit || 'contain',
                 angle: c.options.angle || 0,
                 flip_x: !!c.options.flip_x, flip_y: !!c.options.flip_y };
  const size = c.options.size_uv;
  if (!size || !image) return spec;
  const unit = placeRect(image, box, spec, W, H);
  spec.scale = Math.max(0.05, Math.min(20, size[0] * W / unit.w));
  spec.scale_y = Math.max(0.05, Math.min(20, size[1] * H / unit.h));
  return spec;
}

/**
 * Окно картинок части: стопка слоёв слева, холст, посадка правимого справа
 *
 * Вся стопка живёт ЗДЕСЬ до «Готово»: добавить, заменить, убрать,
 * переставить, выбрать другой слой - правки окна, холст показывает их сразу,
 * а Python склеивает текстуру один раз в конце, одним шагом отмены. Раньше
 * каждое такое действие было своей склейкой и переоткрытием окна
 *
 * `shape` - ответ `part_shape(whole)`: развёртка части, основа без её
 * картинок и сами картинки. `selected` - какой слой правим (отрицательный -
 * с конца), `add` - путь картинки, которая ложится поверх при открытии
 * (брошенная на модель или выбранная файлом). Отвечает новой стопкой или
 * null - ничего не менялось либо нажали «Отмена»
 */
export async function askLayers(shape, selected = -1, add = null) {
  const state = {
    polygons: shape.polygons || [],
    partBox: shape.part_bbox || shape.bbox || [0, 0, 1, 1],
    base: shape.base ? await loadImage(api.fileUrl(shape.base, true)) : null,
    layers: await Promise.all((shape.images || []).map(async (raw) => ({
      spec: layerSpec(raw), image: await loadImage(api.fileUrl(raw.path)) }))),
    sel: -1,
    ticket: 0,
  };
  const initial = JSON.stringify(state.layers.map((l) => l.spec));
  if (add) {
    state.layers.push({ spec: freshSpec(add), image: await loadImage(api.fileUrl(add)) });
  }
  if (!state.layers.length) return null;

  const cv = document.getElementById('place-canvas');
  // Холст - в пропорциях основы: склейка считает «целиком»/«заполнить» в
  // ПИКСЕЛЯХ текстуры, и на квадратном холсте под текстуру 1024×512 картинка
  // вписывалась иначе, чем потом ложилась в мод, а развёртка стояла сжатой.
  // Длинная сторона - 512: размеры ручек считаются в пикселях холста
  const ratio = state.base ? state.base.naturalWidth / state.base.naturalHeight : 1;
  cv.width = Math.round(ratio >= 1 ? 512 : 512 * ratio);
  cv.height = Math.round(ratio >= 1 ? 512 / ratio : 512);
  const wide = document.getElementById('place-w');
  const tall = document.getElementById('place-h');
  const angle = document.getElementById('place-a');
  const shiftX = document.getElementById('place-x');
  const shiftY = document.getElementById('place-y');
  const bare = document.getElementById('place-bare');
  const zoom = document.getElementById('place-zoom');
  const mesh = document.getElementById('place-mesh');
  // Галки показа под холстом - настройки ОКНА, а не предмета, и каждое
  // открытие начинает с одного и того же:
  //  • игровая текстура под наклейкой видна - контекст, хоть и пёстрый;
  //  • сетка треугольников выключена - виден контур детали: сетка из сотен
  //    рёбер закрывала картинку, а нужна только на мелкой детали;
  //  • приближение включено: класть картинку на кусок, глядя на всю
  //    текстуру, - то же, что целиться в спичку с другого конца комнаты
  state.bare = false;
  state.mesh = false;
  state.zoom = true;
  state.zoomK = 1;
  state.focus = null;
  //: Переключатель показа - кнопка-значок: залитая значит «включено»
  const press = (btn, on) => {
    btn.classList.toggle('is-active', on);
    btn.setAttribute('aria-pressed', String(on));
  };
  press(bare, false);
  press(mesh, false);
  press(zoom, true);

  //: Числа в полях - то же самое, что показывает рамка. Тянут её мышью, а
  //: поля обязаны идти следом: иначе они врут о том, что сейчас на холсте.
  // Отражённая по оси - со знаком минус, как в Photoshop: −100% это «тот же
  // размер, перевёрнутая»
  const syncNumbers = () => {
    wide.value = Math.round(state.spec.scale * 100) * (state.spec.flip_x ? -1 : 1);
    tall.value = Math.round(state.spec.scale_y * 100) * (state.spec.flip_y ? -1 : 1);
    angle.value = Math.round(state.spec.angle);
    shiftX.value = Math.round(state.spec.offset[0] * 100);
    shiftY.value = Math.round(state.spec.offset[1] * 100);
  };

  const sync = () => {
    placeDlg.querySelectorAll('[data-fit]').forEach((b) => {
      b.classList.toggle('is-active', b.dataset.fit === state.spec.fit);
    });
    syncNumbers();
    drawPlace(state);
  };

  // Номер - тем же видом, что на чипе в полосе частей: «03», а не «3»
  const chip = document.getElementById('place-part');
  chip.textContent = String(shape.part + 1).padStart(2, '0');
  chip.title = t('Треугольников в развёртке: {}').replace('{}', state.polygons.length);

  return new Promise((resolve) => {
    let done = false;
    const off = [];
    const on = (el, type, fn, opts) => {
      el.addEventListener(type, fn, opts);
      off.push(() => el.removeEventListener(type, fn, opts));
    };
    const stopAnimation = () => {
      if (state.animate) clearInterval(state.animate);
      state.animate = null;
    };

    const settle = (ok) => {
      if (done) return;
      done = true;
      stopAnimation();
      off.forEach((f) => f());
      placeDlg.close();
      const stack = state.layers.map((l) => l.spec);
      resolve(ok && JSON.stringify(stack) !== initial ? stack : null);
    };

    /**
     * Делает слой `n` правимым: рамка, поля и живой кадр - его
     *
     * Кадры анимации Python раскладывает по запросу: браузер их из гифки не
     * достаёт - отсоединённый <img> её не крутит, а drawImage берёт всегда
     * первый. Разбирает их тот же PIL, что и склейка
     */
    const select = async (n) => {
      stopAnimation();
      // Номер вызова: ответ о кадрах, пришедший после следующего выбора,
      // устарел, иначе запускались два таймера и второй никто не гасил
      const ticket = ++state.ticket;
      const layer = state.layers[n];
      // Другой габарит - другое место на текстуре: вид прошлого слоя туда
      // не смотрит
      const box = boxOf(state, layer.spec);
      if (state.bbox && String(state.bbox) !== String(box)) {
        state.zoomK = 1;
        state.focus = null;
      }
      state.sel = n;
      state.spec = layer.spec;
      state.image = layer.image;
      state.bbox = box;
      state.frame = 0;
      state.frames = null;
      renderList();
      sync();
      if (!layer.frames) {
        const path = layer.spec.path;
        const res = await api.imageFrames(path);
        const frames = await Promise.all((res.frames || []).map((f) => loadImage(api.fileUrl(f))));
        // Пока ждали, картинку слоя могли заменить: кадры прежней ему чужие
        if (layer.spec.path !== path) return;
        layer.frames = frames;
        layer.delay = Math.max(30, (res.delays || [])[0] || 100);
      }
      if (done || ticket !== state.ticket || layer.frames.length < 2) return;
      stopAnimation();
      state.frames = layer.frames;
      state.animate = setInterval(() => {
        state.frame += 1;
        drawPlace(state);
      }, layer.delay);
    };

    const renderList = () => showLayers(state, on, {
      pick: (n) => { if (n !== state.sel) select(n); },
      move: (from, to) => {
        if (done) return;
        state.layers.splice(to, 0, ...state.layers.splice(from, 1));
        select(to);
      },
      // Действия на строке выбранного слоя: объявлены ниже, к щелчку уже есть
      replace: () => withFile(true)(),
      copy: () => copy(),
      drop: () => dropLayer(),
    });

    /**
     * Пока картинка грузится, «Готово» ждёт: иначе в Python ушла бы стопка
     * без неё, и слой пропал бы молча
     */
    const okButton = document.getElementById('place-ok');
    const busy = async (work) => {
      okButton.disabled = true;
      try { await work(); } finally { okButton.disabled = false; }
    };

    /** Картинка из файла - новым слоем поверх или на место правимого */
    const placeFile = (file, replace) => busy(async () => {
      let path;
      try {
        path = await api.upload(file);
      } catch (err) {
        hintParts(`Не удалось: ${err.message}`);
        return;
      }
      const image = await loadImage(api.fileUrl(path));
      if (done) return;
      if (replace) {
        // Посадка остаётся: заменяют картинку, а место под неё уже выбрано
        Object.assign(state.layers[state.sel], { image, frames: null });
        state.spec.path = path;
        select(state.sel);
      } else {
        state.layers.push({ spec: freshSpec(path), image });
        select(state.layers.length - 1);
      }
    });

    const paste = () => busy(async () => {
      if (!clip) return;
      const image = await loadImage(api.fileUrl(clip.path));
      if (done) return;
      state.layers.push({ spec: specFromClip(clip, image, state.partBox, cv.width, cv.height),
                          image });
      select(state.layers.length - 1);
    });

    // Тянем картинку мышью: сдвиг считаем в долях места части - в тех же
    // единицах, в которых его понимает склейка.
    // Что делает нажатие - решает место: маркер над картинкой крутит её,
    // всё остальное двигает. Так это устроено в любом редакторе картинок, и
    // отдельного циферблата для поворота не нужно
    const rectNow = () => {
      const shown = shownImage(state);
      return shown ? placeRect(shown, state.bbox, state.spec, cv.width, cv.height) : null;
    };

    let drag = null;
    on(cv, 'pointerdown', (e) => {
      cv.focus();
      const rect = rectNow();
      if (!rect) return;
      cv.setPointerCapture(e.pointerId);
      const [lx, ly, k] = localPoint(state, rect, e.clientX, e.clientY, cv);
      const handleY = -rect.h / 2 - HANDLE_GAP / k;
      const near = Math.hypot(lx, ly - handleY) <= (HANDLE_R + 6) / k;
      // Что делает нажатие, решает место: маркер над картинкой крутит,
      // квадратик на рамке тянет размер, всё остальное двигает
      const grip = near ? null : gripAt(rect, lx, ly, k);
      if (near) drag = { turn: true };
      else if (grip) {
        drag = { grip, rect, w0: rect.w, h0: rect.h,
                 scale0: state.spec.scale, scaleY0: state.spec.scale_y,
                 flipX0: state.spec.flip_x, flipY0: state.spec.flip_y,
                 off0: [...state.spec.offset] };
      } else {
        drag = { x: e.clientX, y: e.clientY, from: [...state.spec.offset] };
      }
    });
    on(cv, 'pointermove', (e) => {
      if (!drag) return;
      const rect = rectNow();
      if (!rect) return;
      if (drag.turn) {
        // Угол - от центра картинки к курсору. Маркер стоит НАД картинкой,
        // поэтому ноль там же, где он: atan2(dx, -dy), а не наоборот
        const [lx, ly] = localPoint(state, rect, e.clientX, e.clientY, cv);
        const rad = state.spec.angle * Math.PI / 180;
        const dx = lx * Math.cos(rad) - ly * Math.sin(rad);
        const dy = lx * Math.sin(rad) + ly * Math.cos(rad);
        let angle = (Math.atan2(dx, -dy) * 180 / Math.PI + 360) % 360;
        // Прямые углы подтягиваются: попасть мышью ровно в 90° иначе нельзя,
        // а нужны они чаще всего
        const step = Math.round(angle / 15) * 15;
        if (Math.abs(angle - step) < 3) angle = step % 360;
        state.spec.angle = angle;
        drawPlace(state);
        syncNumbers();
        return;
      }
      if (drag.grip) { resizeBy(state, drag, e, cv); syncNumbers(); return; }
      const r = cv.getBoundingClientRect();
      // Приближение меняет экранный размер места части: без множителя картинка
      // при перетаскивании убегала бы от курсора во столько же раз
      const k = placeView(state, cv.width, cv.height).k;
      const bw = Math.max(1e-3, (state.bbox[2] - state.bbox[0]) * r.width * k);
      const bh = Math.max(1e-3, (state.bbox[3] - state.bbox[1]) * r.height * k);
      state.spec.offset = [drag.from[0] + (e.clientX - drag.x) / bw,
                           drag.from[1] + (e.clientY - drag.y) / bh];
      drawPlace(state);
      syncNumbers();
    });
    on(cv, 'pointerup', (e) => { cv.releasePointerCapture(e.pointerId); drag = null; });
    // Колесо приближает ВИД: подойти к нужному островку иначе нечем.
    // Приближаем к курсору, как в картах, - тогда панорамирование не нужно
    // вовсе. С Ctrl колесо меняет размер картинки, пропорционально
    on(cv, 'wheel', (e) => {
      e.preventDefault();
      if (e.ctrlKey || e.metaKey) {
        const k = e.deltaY < 0 ? 1.06 : 1 / 1.06;
        const clamp = (v) => Math.max(0.05, Math.min(20, v * k));
        state.spec.scale = clamp(state.spec.scale);
        state.spec.scale_y = clamp(state.spec.scale_y);
        drawPlace(state);
        syncNumbers();
        return;
      }
      if (!state.zoom) return;
      const W = cv.width;
      const H = cv.height;
      const r = cv.getBoundingClientRect();
      const at = [(e.clientX - r.left) / r.width * W,
                  (e.clientY - r.top) / r.height * H];
      const was = placeView(state, W, H);
      // Точка текстуры под курсором - она и должна остаться под ним
      const tex = [(at[0] - was.dx) / was.k, (at[1] - was.dy) / was.k];
      state.zoomK = Math.max(1, Math.min(12,
        (state.zoomK || 1) * (e.deltaY < 0 ? 1.15 : 1 / 1.15)));
      const now = placeView({ ...state, focus: tex }, W, H);
      state.focus = [tex[0] - (at[0] - W / 2) / now.k,
                     tex[1] - (at[1] - H / 2) / now.k];
      drawPlace(state);
    }, { passive: false });

    on(placeDlg, 'click', (e) => {
      const fit = e.target.closest('[data-fit]');
      if (!fit) return;
      state.spec.fit = fit.dataset.fit;
      // Строка слоя пишет, как он вписан
      renderList();
      sync();
    });

    // Копировать - картинку и её посадку с размером на ТЕКСТУРЕ; вставить -
    // новым слоем на эту же часть (на другую - кнопкой на её чипе)
    const pasteButton = document.getElementById('place-paste');
    pasteButton.disabled = !clip;
    const copy = () => {
      const rect = rectNow();
      const { path } = state.spec;
      if (!rect || !path) return;
      remember({ path, name: String(path).split(/[\\/]/).pop(),
                 options: { fit: state.spec.fit, angle: state.spec.angle,
                            flip_x: state.spec.flip_x, flip_y: state.spec.flip_y,
                            size_uv: [rect.w / cv.width, rect.h / cv.height] } });
      pasteButton.disabled = false;
      hintParts('Картинка скопирована. На другую часть - наведи на неё на модели и нажми Ctrl+V');
    };
    on(pasteButton, 'click', paste);

    // Поворот стрелками: маркер мышкой - привычно, но не единственный способ
    // должен быть у того, кто мышью не работает
    on(cv, 'keydown', (e) => {
      if ((e.ctrlKey || e.metaKey) && e.code === 'KeyC') { e.preventDefault(); copy(); return; }
      if ((e.ctrlKey || e.metaKey) && e.code === 'KeyV' && clip) {
        e.preventDefault();
        paste();
        return;
      }
      const step = { ArrowLeft: -15, ArrowDown: -15, ArrowRight: 15, ArrowUp: 15 }[e.key];
      if (step === undefined) return;
      e.preventDefault();
      state.spec.angle = ((state.spec.angle + step) % 360 + 360) % 360;
      drawPlace(state);
      syncNumbers();
    });

    // Поля - для точного числа, мышью то же самое делают ручки на рамке.
    // Минус в поле - отражение по этой оси
    const byNumber = (field, axis, flip) => on(field, 'input', () => {
      const value = Number(field.value) / 100;
      if (!value || !Number.isFinite(value)) return;   // пустое - человек его чистит
      state.spec[axis] = Math.max(0.05, Math.min(20, Math.abs(value)));
      state.spec[flip] = value < 0;
      drawPlace(state);
    });
    byNumber(wide, 'scale', 'flip_x');
    byNumber(tall, 'scale_y', 'flip_y');
    // Поворот и сдвиг числом: то же, что маркер и перетаскивание, только точно
    on(angle, 'input', () => {
      const value = Number(angle.value);
      if (!Number.isFinite(value) || angle.value === '') return;
      state.spec.angle = ((value % 360) + 360) % 360;
      drawPlace(state);
    });
    const byShift = (field, axis) => on(field, 'input', () => {
      const value = Number(field.value);
      if (!Number.isFinite(value) || field.value === '') return;
      const offset = [...state.spec.offset];
      offset[axis] = Math.max(-5, Math.min(5, value / 100));
      state.spec.offset = offset;
      drawPlace(state);
    });
    byShift(shiftX, 0);
    byShift(shiftY, 1);
    on(bare, 'click', () => {
      state.bare = !state.bare;
      press(bare, state.bare);
      drawPlace(state);
    });
    on(mesh, 'click', () => {
      state.mesh = !state.mesh;
      press(mesh, state.mesh);
      drawPlace(state);
    });
    on(zoom, 'click', () => {
      state.zoom = !state.zoom;
      press(zoom, state.zoom);
      state.zoomK = 1;             // выключили и включили - вид снова стартовый
      state.focus = null;
      drawPlace(state);
    });

    // Панель над холстом: то, что мышью делается жестом, который надо знать.
    // Посадку меняем НА МЕСТЕ: запись слоя - та же, что лежит в стопке
    const tool = (id, change) => on(document.getElementById(id), 'click', () => {
      change(state.spec);
      sync();
    });
    tool('place-rotl', (s) => { s.angle = ((s.angle - 90) % 360 + 360) % 360; });
    tool('place-rotr', (s) => { s.angle = (s.angle + 90) % 360; });
    tool('place-flipx', (s) => { s.flip_x = !s.flip_x; });
    tool('place-flipy', (s) => { s.flip_y = !s.flip_y; });
    tool('place-center', (s) => { s.offset = [0, 0]; });
    tool('place-reset', (s) => {
      Object.assign(s, freshSpec(s.path));
      state.zoomK = 1;
      state.focus = null;
    });

    // Файл спрашиваем до правки: отказ от выбора ничего не меняет
    const withFile = (replace) => async () => {
      const file = await chooseFile('image/*,.vtf');
      if (file) placeFile(file, replace);
    };
    on(document.getElementById('place-add'), 'click', withFile(false));
    const dropLayer = () => {
      state.layers.splice(state.sel, 1);
      // Сняли последнюю - править больше нечего, это и есть ответ
      if (!state.layers.length) { settle(true); return; }
      select(Math.min(state.sel, state.layers.length - 1));
    };

    // Файл, брошенный на холст, ложится новым слоем. Событие гасим здесь:
    // иначе его поймала бы страница под окном и положила картинку на модель
    const stage = document.getElementById('place-stage');
    const isFile = (e) => [...(e.dataTransfer?.types || [])].includes('Files');
    on(stage, 'dragover', (e) => {
      if (!isFile(e)) return;
      e.preventDefault();
      e.stopPropagation();
      stage.classList.add('is-drop');
    });
    on(stage, 'dragleave', (e) => {
      if (!stage.contains(e.relatedTarget)) stage.classList.remove('is-drop');
    });
    on(stage, 'drop', (e) => {
      if (!isFile(e)) return;
      e.preventDefault();
      e.stopPropagation();
      stage.classList.remove('is-drop');
      const file = e.dataTransfer.files[0];
      if (file) placeFile(file, false);
    });

    on(document.getElementById('place-ok'), 'click', () => settle(true));
    on(document.getElementById('place-cancel'), 'click', () => settle(false));
    on(placeDlg, 'cancel', (e) => { e.preventDefault(); settle(false); });

    const n = state.layers.length;
    select(add ? n - 1 : ((selected % n) + n) % n);
    if (!placeDlg.open) placeDlg.showModal();
  });
}

let editing = false;

/**
 * Редактор картинок части: окно со стопкой слоёв
 *
 * Открывается на слое `layer` (отрицательный - с конца). `add` - путь
 * картинки, которая ложится поверх при открытии: брошенная на модель или
 * выбранная файлом. Всё, что сделано в окне, уходит в Python одним вызовом
 * по «Готово» - одна склейка и один шаг Ctrl+Z. «Отмена» бросает всё,
 * включая только что брошенную картинку
 */
export async function editPartLayers(part, layer = -1, add = null) {
  // Окно одно на всё приложение: второй вызов, пока первое открывается
  // (двойной щелчок, второй бросок), повесил бы на те же кнопки вторую стопку
  if (editing) return;
  editing = true;
  let stack;
  try {
    const shape = await api.partShape(P.material, part, null, true);
    if (shape.error) { hintParts(shape.error); return; }
    stack = await askLayers(shape, layer, add);
  } finally {
    editing = false;
  }
  if (!stack) return;
  hintParts(stack.length ? 'Наложение на часть…' : 'Убираю…');
  const res = await api.setPartLayers(P.material, part, stack);
  if (res.error) { hintParts(res.error); return; }
  applyView(res);
  const fresh = await refreshParts();
  // Куски, делящие развёртку, красятся вместе. Сказать об этом надо в тот
  // момент, когда это произошло, а не только подсказкой на кнопке
  const painted = ((fresh && fresh.parts) || []).find((p) => p.id === part);
  hintParts(stack.length && painted && painted.shared.length
    ? 'Эта часть делит развёртку с соседними - они покрасились вместе'
    : '');
}

/** Одно действие над картинками части вне окна - и модель с полосой следом */
async function persist(part, path, options, layer) {
  hintParts(path ? 'Наложение на часть…' : 'Перекладываю…');
  const res = await api.setPartTexture(P.material, part, path, options, layer);
  if (res.error) { hintParts(res.error); return false; }
  applyView(res);
  await refreshParts();
  hintParts('');
  return true;
}
