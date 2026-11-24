/*
 * Как положить оружие на обложке: остриё или ствол влево, рукоять вниз
 *
 * Общего «вперёд» у моделей нет: модель TF2 крепится к кости руки, и у разных
 * модов длинная ось смотрит куда угодно, бывает и наискось к осям сцены.
 * Поэтому оси берём из самой формы (главные оси облака вершин), а концы
 * различаем по толщине: остриё и ствол тоньше рукояти и приклада.
 *
 * Чистая математика без three.js: точки - плоский массив [x, y, z, ...]
 */

//: Доли длины с каждого конца, по которым сравнивается толщина: сперва
//: самый кончик, потом конец пошире
const TIP_ZONE = 0.03;
const END_ZONE = 0.2;
//: Во сколько раз один кончик должен быть толще другого, чтобы им поверить
const TIP_RATIO = 1.5;

//: Ниже этого совпадения с подсказкой (косинус) ось ей не верит и решает форма
const PRIOR_MIN = 0.3;

/**
 * Оси кадра {right, up, back}: right - от острия к рукояти (на экране
 * вправо), up - вверх экрана, back - на зрителя. null - точек нет
 *
 * prior {forward, up} - куда у модели обычно смотрит перёд и верх. Форма
 * даёт только оси, а стороны по форме угадываются плохо: торец ствола бывает
 * толще кончика приклада. Подсказка решает сторону, если ось с ней хоть
 * как-то совпадает; иначе - форма
 */
export function itemPose(points, prior = null) {
  const n = Math.floor(points.length / 3);
  if (n < 2) return null;

  const mean = [0, 0, 0];
  for (let i = 0; i < n * 3; i += 3) {
    for (let k = 0; k < 3; k++) mean[k] += points[i + k] / n;
  }
  const cov = [[0, 0, 0], [0, 0, 0], [0, 0, 0]];
  for (let i = 0; i < n * 3; i += 3) {
    const d = [points[i] - mean[0], points[i + 1] - mean[1], points[i + 2] - mean[2]];
    for (let r = 0; r < 3; r++) for (let c = 0; c < 3; c++) cov[r][c] += d[r] * d[c] / n;
  }
  const [a1, a2] = eigenSym3(cov).map((e) => e.vector);
  const [long, mid] = _straighten(points, mean, a1, a2);

  const t = _project(points, mean, long);
  const s = _project(points, mean, mid);
  const flip = (v) => v.map((x) => -x);
  const f = prior ? _dot(long, prior.forward) : 0;
  // Перёд уходит влево, значит right смотрит назад
  const right = Math.abs(f) >= PRIOR_MIN ? (f > 0 ? flip(long) : long)
    : (_tipAtLow(t, s) ? long : flip(long));

  // Рукоять - одинокий выступ вбок: дальний край по средней оси с той
  // стороны, где точек меньше. Она уходит вниз
  const [sLo, sHi] = _range(s);
  const u = prior ? _dot(mid, prior.up) : 0;
  const up = Math.abs(u) >= PRIOR_MIN ? (u > 0 ? mid : flip(mid))
    : (sHi > -sLo ? flip(mid) : mid);

  return { right, up, back: _cross(right, up) };
}

/** Собственные числа и векторы симметричной 3x3 (Якоби), по убыванию */
export function eigenSym3(m) {
  const a = m.map((row) => row.slice());
  const v = [[1, 0, 0], [0, 1, 0], [0, 0, 1]];
  for (let sweep = 0; sweep < 50; sweep++) {
    if (Math.abs(a[0][1]) + Math.abs(a[0][2]) + Math.abs(a[1][2]) < 1e-12) break;
    for (const [p, q] of [[0, 1], [0, 2], [1, 2]]) {
      if (Math.abs(a[p][q]) < 1e-15) continue;
      const theta = (a[q][q] - a[p][p]) / (2 * a[p][q]);
      const tan = (theta >= 0 ? 1 : -1) / (Math.abs(theta) + Math.sqrt(theta * theta + 1));
      const c = 1 / Math.sqrt(tan * tan + 1);
      const s = tan * c;
      const turn = (get, set) => {
        for (let k = 0; k < 3; k++) {
          const x = get(k, p);
          const y = get(k, q);
          set(k, p, c * x - s * y);
          set(k, q, s * x + c * y);
        }
      };
      turn((k, i) => a[k][i], (k, i, x) => { a[k][i] = x; });
      turn((k, i) => a[i][k], (k, i, x) => { a[i][k] = x; });
      turn((k, i) => v[k][i], (k, i, x) => { v[k][i] = x; });
    }
  }
  return [0, 1, 2]
    .map((i) => ({ value: a[i][i], vector: [v[0][i], v[1][i], v[2][i]] }))
    .sort((x, y) => y.value - x.value);
}

/**
 * Остриё (ствол) на нижнем конце длинной оси?
 *
 * t - положение точек вдоль длинной оси, s - поперёк. Сначала сравниваем сами
 * кончики: остриё почти точка, а навершие, кольцо, приклад - нет. Выступы у
 * острия (петли на клинке) до кончика не достают. Кончики одинаковые, как у
 * пистолета, - решает конец пошире: в него попадает рукоять
 */
function _tipAtLow(t, s) {
  const [lo, hi] = _range(t);
  const spread = (inEnd) => {
    let a = Infinity;
    let b = -Infinity;
    t.forEach((v, i) => { if (inEnd(v)) { a = Math.min(a, s[i]); b = Math.max(b, s[i]); } });
    return b > a ? b - a : 0;
  };
  const ends = (frac) => {
    const zone = (hi - lo) * frac;
    return [spread((v) => v <= lo + zone), spread((v) => v >= hi - zone)];
  };
  const [a, b] = ends(TIP_ZONE);
  if (Math.max(a, b) > TIP_RATIO * Math.min(a, b)) return a < b;
  const [wa, wb] = ends(END_ZONE);
  return wa <= wb;
}

/**
 * Длинная и средняя оси без перекоса
 *
 * Главная ось облака тянется к массе: тяжёлая рукоять наклоняла пистолет
 * градусов на двадцать. Ровнее всего форма лежит в прямоугольнике наименьшей
 * площади - у Г-образного пистолета он идёт вдоль ствола. Ищем его поворотом
 * в плоскости двух главных осей
 */
function _straighten(points, mean, a1, a2) {
  const x = _project(points, mean, a1);
  const y = _project(points, mean, a2);
  let best = { area: Infinity, angle: 0, wide: true };
  for (let deg = -45; deg < 45; deg += 0.5) {
    const c = Math.cos(deg * Math.PI / 180);
    const s = Math.sin(deg * Math.PI / 180);
    let [uLo, uHi, vLo, vHi] = [Infinity, -Infinity, Infinity, -Infinity];
    for (let i = 0; i < x.length; i++) {
      const u = x[i] * c + y[i] * s;
      const v = y[i] * c - x[i] * s;
      if (u < uLo) uLo = u; if (u > uHi) uHi = u;
      if (v < vLo) vLo = v; if (v > vHi) vHi = v;
    }
    const area = (uHi - uLo) * (vHi - vLo);
    if (area < best.area - 1e-12) best = { area, angle: deg, wide: uHi - uLo >= vHi - vLo };
  }
  const c = Math.cos(best.angle * Math.PI / 180);
  const s = Math.sin(best.angle * Math.PI / 180);
  const u = a1.map((v, k) => v * c + a2[k] * s);
  const v = a2.map((w, k) => w * c - a1[k] * s);
  return best.wide ? [u, v] : [v, u];
}

function _project(points, origin, axis) {
  const out = [];
  for (let i = 0; i + 2 < points.length; i += 3) {
    out.push((points[i] - origin[0]) * axis[0] + (points[i + 1] - origin[1]) * axis[1]
             + (points[i + 2] - origin[2]) * axis[2]);
  }
  return out;
}

// Не Math.min(...arr): у модели десятки тысяч вершин, а у разворота в
// аргументы есть предел
function _range(arr) {
  let a = Infinity;
  let b = -Infinity;
  for (const v of arr) { if (v < a) a = v; if (v > b) b = v; }
  return [a, b];
}

function _dot(a, b) {
  return a[0] * b[0] + a[1] * b[1] + a[2] * b[2];
}

function _cross(a, b) {
  return [a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]];
}
