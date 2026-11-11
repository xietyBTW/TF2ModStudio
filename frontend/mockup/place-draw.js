/*
 * Холст окна посадки: геометрия картинки на развёртке и рисование стопки
 *
 * Расчёт повторяет `texture_compose_service.place_image`: тот же порядок
 * (размер -> поворот -> место) и тот же знак угла. Разойтись им нельзя - человек
 * настраивает по одному изображению, а в мод уйдёт другое. Состояние окна
 * держит place.js, здесь только чистые расчёты и рисование по нему
 */

/**
 * Куда и какого размера ляжет картинка - в пикселях холста развёртки
 *
 * Холст повторяет ПРОПОРЦИИ текстуры (W × H), а не квадрат: у тела шпиона
 * она 1024×512, и на квадрате развёртка сжималась вдвое по ширине, а
 * «целиком» вписывалось не так, как это потом делала склейка в пикселях.
 */
export function placeRect(image, box, spec, W, H) {
  const bw = Math.max(1, (box[2] - box[0]) * W);
  const bh = Math.max(1, (box[3] - box[1]) * H);
  let w = bw;
  let h = bh;
  if (spec.fit !== 'stretch') {
    const k = spec.fit === 'cover'
      ? Math.max(bw / image.width, bh / image.height)
      : Math.min(bw / image.width, bh / image.height);
    w = image.width * k;
    h = image.height * k;
  }
  w *= spec.scale;
  // По высоте - свой множитель: за угол рамки тянут целиком, за сторону -
  // только по её оси. Старые работы второго не знают: там он равен первому
  h *= (spec.scale_y === undefined ? spec.scale : spec.scale_y);
  // Развёртка считает v снизу, холст - сверху: место части переворачивается
  const cx = box[0] * W + bw / 2 + spec.offset[0] * bw;
  const cy = (1 - box[3]) * H + bh / 2 + spec.offset[1] * bh;
  return { x: cx, y: cy, w, h };
}

/**
 * Как холст показывает развёртку: целиком или вплотную к правимому куску
 *
 * Всё рисование остаётся в координатах ТЕКСТУРЫ (0..size), приближение -
 * одно преобразование холста поверх. Иначе масштаб пришлось бы вносить в
 * каждую формулу, и посадка картинки разъехалась бы с тем, что считает Python
 *
 * Приближаем РОВНО к габариту части - тому самому, в который вписана картинка.
 * «Плотный» габарит без 4% площади с краёв не годится: картинка ложится в
 * ПОЛНЫЙ, и у праздничного огнетопора в вид не попадало бы до половины
 * треугольников части
 *
 * Автоматика не угадает, какой островок нужен человеку, поэтому она только
 * ставит СТАРТОВЫЙ вид, а дальше он приближает колесом.
 */
export function placeView(state, W, H) {
  if (!state.zoom) return { k: 1, dx: 0, dy: 0 };
  const b = state.bbox;
  const w = Math.max(1, (b[2] - b[0]) * W);
  const h = Math.max(1, (b[3] - b[1]) * H);
  // Запас по краям: деталь, прижатая к самой рамке, читается хуже, а картинку
  // нередко двигают чуть за край куска. Меньше единицы не опускаемся - окно
  // называется «приблизить», отдалять оно не должно
  const fit = Math.max(1, Math.min(W / w, H / h) * 0.86);
  const k = fit * (state.zoomK || 1);
  const focus = state.focus
    || [b[0] * W + w / 2, (1 - b[3]) * H + h / 2];
  return { k, dx: W / 2 - k * focus[0], dy: H / 2 - k * focus[1] };
}

/**
 * Внешний контур развёртки: рёбра, у которых нет пары
 *
 * Развёртка приезжает ТРЕУГОЛЬНИКАМИ, и обвести каждый - значит нарисовать
 * сетку: у детали из полутора тысяч треугольников за ней не видно ни картинки,
 * ни собственных краёв. Внутреннее ребро принадлежит двум треугольникам сразу,
 * граничное - одному: пары взаимно уничтожаются, остаётся контур. Островов у
 * куска бывает несколько - контуров тогда столько же, и это правда о нём.
 */
function outlineOf(polygons) {
  const edges = new Map();
  for (const tri of polygons) {
    for (let i = 0; i < 3; i++) {
      const from = tri[i];
      const to = tri[(i + 1) % 3];
      const a = from[0] + ',' + from[1];
      const b = to[0] + ',' + to[1];
      const key = a < b ? a + '|' + b : b + '|' + a;
      if (edges.has(key)) edges.delete(key);
      else edges.set(key, [from, to]);
    }
  }
  return [...edges.values()];
}

/** Габарит, в который вписан слой: свой якорь (пережил разрез) или часть */
export const boxOf = (state, spec) => spec.anchor || state.partBox;

/** Что сейчас показывает правимый слой: кадр анимации или саму картинку */
export function shownImage(state) {
  return (state.frames && state.frames.length)
    ? state.frames[state.frame % state.frames.length]
    : state.image;
}

/**
 * Маска части путём холста - тем же набором треугольников, по которому
 * маскирует склейка. Строится один раз: треугольники за время окна не
 * меняются, а режет она каждый слой
 *
 * Обход у всех треугольников разворачиваем В ОДНУ сторону. Холст заливает
 * путь по правилу nonzero: пара треугольников, лежащих друг на друге с
 * противоположным обходом, даёт число оборотов 0 - то есть ДЫРУ. А в TF2
 * зеркальные половины модели делят одну развёртку сплошь: у праздничного
 * огнетопора таких треугольников 253 из 1249. Склейка этим не болеет - она
 * заливает каждый треугольник отдельно (PIL), поэтому врал бы только показ
 */
function partPath(state, W, H) {
  if (state.clip && state.clipSize === W + 'x' + H) return state.clip;
  const path = new Path2D();
  for (const [a, b, c] of state.polygons) {
    // Знак площади считаем в координатах РАЗВЁРТКИ; холст переворачивает v,
    // и знак вместе с ним, поэтому порядок выбираем по «< 0»
    const area = (b[0] - a[0]) * (c[1] - a[1]) - (c[0] - a[0]) * (b[1] - a[1]);
    const [p, q, r] = area < 0 ? [a, b, c] : [a, c, b];
    path.moveTo(p[0] * W, (1 - p[1]) * H);
    path.lineTo(q[0] * W, (1 - q[1]) * H);
    path.lineTo(r[0] * W, (1 - r[1]) * H);
    path.closePath();
  }
  state.clip = path;
  state.clipSize = W + 'x' + H;
  return path;
}

function drawPicture(g, image, rect, spec) {
  g.save();
  g.translate(rect.x, rect.y);
  g.rotate(spec.angle * Math.PI / 180);
  // Отражение - по осям самой картинки, до поворота: так же его делает
  // склейка (place_image), иначе окно и мод разошлись бы
  g.scale(spec.flip_x ? -1 : 1, spec.flip_y ? -1 : 1);
  g.drawImage(image, -rect.w / 2, -rect.h / 2, rect.w, rect.h);
  g.restore();
}

export function drawPlace(state) {
  const cv = document.getElementById('place-canvas');
  const g = cv.getContext('2d');
  const W = cv.width;
  const H = cv.height;
  g.setTransform(1, 0, 0, 1, 0, 0);
  g.clearRect(0, 0, W, H);

  const view = placeView(state, W, H);
  g.setTransform(view.k, 0, 0, view.k, view.dx, view.dy);
  // Масштаб вида - рядом с подсказкой: колесо меняет его, а без числа не
  // понять, насколько близко подошёл
  document.getElementById('place-zoomk').textContent = Math.round(view.k * 100) + '%';

  // Основа - материал БЕЗ картинок этой части: всю стопку окно рисует само,
  // снизу вверх, так же как её потом положит склейка
  if (state.base && !state.bare) g.drawImage(state.base, 0, 0, W, H);

  const clip = partPath(state, W, H);
  let rect = null;
  state.layers.forEach((layer, i) => {
    const live = i === state.sel;
    const image = live ? shownImage(state) : layer.image;
    if (!image) return;
    const r = placeRect(image, boxOf(state, layer.spec), layer.spec, W, H);
    if (live) rect = r;
    // Без игровой текстуры правимую картинку показываем ЦЕЛИКОМ: призраком -
    // то, что при сборке отрежется, в полную силу - то, что доживёт
    if (live && state.bare) {
      g.save();
      g.globalAlpha = 0.28;
      drawPicture(g, image, r, layer.spec);
      g.restore();
    }
    g.save();
    g.clip(clip);
    drawPicture(g, image, r, layer.spec);
    g.restore();
  });

  // Всё, что вне детали, притемняем: пёстрая текстура вокруг спорила с
  // картинкой, и было не видно, куда она ляжет. Тёмный слой рисуем на
  // отдельном холсте и вырезаем из него деталь
  const veil = state.veil || (state.veil = document.createElement('canvas'));
  veil.width = W;
  veil.height = H;
  const v = veil.getContext('2d');
  v.setTransform(1, 0, 0, 1, 0, 0);
  v.fillStyle = 'rgba(10, 9, 8, 0.55)';
  v.fillRect(0, 0, W, H);
  v.setTransform(view.k, 0, 0, view.k, view.dx, view.dy);
  v.globalCompositeOperation = 'destination-out';
  v.fill(clip);
  g.save();
  g.setTransform(1, 0, 0, 1, 0, 0);
  g.drawImage(veil, 0, 0);
  g.restore();

  // Контур маски поверх всего: без него не видно, докуда картинка доживёт.
  // Толщину делим на масштаб - иначе при приближении он превращается в брус
  g.strokeStyle = '#cc5522';
  g.lineWidth = 1 / view.k;
  g.beginPath();
  if (!state.mesh) {
    // Считаем один раз: треугольники за время окна не меняются
    if (!state.edges) state.edges = outlineOf(state.polygons);
    for (const [from, to] of state.edges) {
      g.moveTo(from[0] * W, (1 - from[1]) * H);
      g.lineTo(to[0] * W, (1 - to[1]) * H);
    }
  } else {
    for (const tri of state.polygons) {
      g.moveTo(tri[0][0] * W, (1 - tri[0][1]) * H);
      g.lineTo(tri[1][0] * W, (1 - tri[1][1]) * H);
      g.lineTo(tri[2][0] * W, (1 - tri[2][1]) * H);
      g.closePath();
    }
  }
  g.stroke();

  if (rect) drawHandle(g, rect, state.spec.angle, view.k);
  g.setTransform(1, 0, 0, 1, 0, 0);
}

//: Маркер поворота: отступ от края картинки и радиус - в пикселях ХОЛСТА
//: (деление на масштаб вида гасит приближение, поэтому размер постоянный).
//: Холст (длинная сторона 512) показывается примерно в 330 CSS-пикселях, то
//: есть всё это ещё и сжимается на треть - отсюда числа крупнее, чем кажется
//: нужным
export const HANDLE_GAP = 38;
export const HANDLE_R = 10;
//: Сторона квадратика на рамке и радиус попадания по нему. Попадание крупнее
//: самого квадратика: целиться в семь пикселей мышью - работа, а не правка
const GRIP = 9;
const GRIP_HIT = 14;

//: Ручки рамки: углы и середины сторон. Знаки говорят, какой край тянут, и
//: они же дают точку, которая при этом остаётся на месте (противоположная)
const GRIPS = [[-1, -1], [1, -1], [1, 1], [-1, 1],
               [0, -1], [1, 0], [0, 1], [-1, 0]];

/** Ручка под курсором в системе картинки. null - курсор не на ручке */
export function gripAt(rect, lx, ly, k) {
  const reach = GRIP_HIT / k;
  let best = null;
  for (const [sx, sy] of GRIPS) {
    const gap = Math.hypot(lx - sx * rect.w / 2, ly - sy * rect.h / 2);
    if (gap <= reach && (!best || gap < best.gap)) best = { sx, sy, gap };
  }
  return best;
}

/** Рамка картинки и маркер поворота над ней - привычная ручка, а не циферблат */
function drawHandle(g, rect, angle, k) {
  const gap = HANDLE_GAP / k;
  const radius = HANDLE_R / k;
  g.save();
  g.translate(rect.x, rect.y);
  g.rotate(angle * Math.PI / 180);
  g.strokeStyle = '#cc5522';
  g.lineWidth = 1.5 / k;
  g.setLineDash([7 / k, 5 / k]);
  g.strokeRect(-rect.w / 2, -rect.h / 2, rect.w, rect.h);
  g.setLineDash([]);
  g.beginPath();
  g.moveTo(0, -rect.h / 2);
  g.lineTo(0, -rect.h / 2 - gap);
  g.stroke();
  // Заливка акцентом, обводка белым, а не наоборот: маркер висит над самой
  // картинкой, и белый кружок терялся на светлых наклейках
  g.beginPath();
  g.arc(0, -rect.h / 2 - gap, radius, 0, Math.PI * 2);
  g.fillStyle = '#cc5522';
  g.fill();
  g.strokeStyle = '#fff';
  g.lineWidth = 2 / k;
  g.stroke();

  // Ручки размера - там же, где их ищет рука: по углам и серединам сторон.
  // Белая заливка с акцентной обводкой: они лежат на самой картинке, и
  // сплошной акцент на оранжевой наклейке пропадал бы
  const side = GRIP / k;
  g.lineWidth = 1.5 / k;
  for (const [sx, sy] of GRIPS) {
    g.beginPath();
    g.rect(sx * rect.w / 2 - side / 2, sy * rect.h / 2 - side / 2, side, side);
    g.fillStyle = '#fff';
    g.fill();
    g.strokeStyle = '#cc5522';
    g.stroke();
  }
  g.restore();
}

/** Точка холста в системе КАРТИНКИ: центр в нуле, поворот снят */
export function localPoint(state, rect, clientX, clientY, cv) {
  const view = placeView(state, cv.width, cv.height);
  const r = cv.getBoundingClientRect();
  const tex = [((clientX - r.left) / r.width * cv.width - view.dx) / view.k,
               ((clientY - r.top) / r.height * cv.height - view.dy) / view.k];
  const rad = -state.spec.angle * Math.PI / 180;
  const dx = tex[0] - rect.x;
  const dy = tex[1] - rect.y;
  return [dx * Math.cos(rad) - dy * Math.sin(rad),
          dx * Math.sin(rad) + dy * Math.cos(rad), view.k];
}


/**
 * Тянет рамку за ручку
 *
 * Противоположный край стоит на месте - так это работает в редакторах
 * изображений: тянешь правый край, левый не шевелится. Значит меняется не
 * только размер, но и центр, а центр здесь живёт в сдвиге (`offset`), в долях
 * места части
 *
 * Протянул край ЗА противоположный - картинка отражается по этой оси, как в
 * Photoshop: отдельной кнопки «отразить» нет, это то же движение руки
 *
 * Угол тянет обе оси разом, сохраняя пропорции: чаще всего наклейку просто
 * увеличивают. Сторона тянет свою - ею картинку и вытягивают под деталь.
 */
export function resizeBy(state, drag, event, cv) {
  const { sx, sy } = drag.grip;
  // Считаем в системе рамки НА МОМЕНТ НАЖАТИЯ: она не должна ехать вслед за
  // собственным изменением, иначе тяга разгоняется сама по себе
  const [lx, ly] = localPoint(state, drag.rect, event.clientX, event.clientY, cv);
  // Размер со ЗНАКОМ, от неподвижного края: меньше нуля - край протащили за
  // противоположный
  let sw = sx ? sx * lx + drag.w0 / 2 : drag.w0;
  let sh = sy ? sy * ly + drag.h0 / 2 : drag.h0;
  if (sx && sy) {
    const k = Math.hypot(sw, sh) / Math.hypot(drag.w0, drag.h0);
    sw = (sw < 0 ? -1 : 1) * drag.w0 * k;
    sh = (sh < 0 ? -1 : 1) * drag.h0 * k;
  }
  const w = Math.max(4, Math.abs(sw));
  const h = Math.max(4, Math.abs(sh));
  const dirX = sw < 0 ? -1 : 1;
  const dirY = sh < 0 ? -1 : 1;

  const clamp = (value) => Math.max(0.05, Math.min(20, value));
  state.spec.scale = clamp(drag.scale0 * w / drag.w0);
  state.spec.scale_y = clamp(drag.scaleY0 * h / drag.h0);
  state.spec.flip_x = drag.flipX0 !== (dirX < 0);
  state.spec.flip_y = drag.flipY0 !== (dirY < 0);

  // Новый центр - посередине между неподвижным краем и тем, что тянут
  const shiftX = sx ? -sx * drag.w0 / 2 + sx * dirX * w / 2 : 0;
  const shiftY = sy ? -sy * drag.h0 / 2 + sy * dirY * h / 2 : 0;
  const rad = state.spec.angle * Math.PI / 180;
  const worldX = shiftX * Math.cos(rad) - shiftY * Math.sin(rad);
  const worldY = shiftX * Math.sin(rad) + shiftY * Math.cos(rad);
  const bw = Math.max(1, (state.bbox[2] - state.bbox[0]) * cv.width);
  const bh = Math.max(1, (state.bbox[3] - state.bbox[1]) * cv.height);
  state.spec.offset = [drag.off0[0] + worldX / bw, drag.off0[1] + worldY / bh];
  drawPlace(state);
}
