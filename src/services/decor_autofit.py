"""
Автоподгонка гирлянды под свою модель оружия

Игра вешает гирлянду по стоковой пушке, и на своей модели огоньки тонут в
ней или висят в воздухе. Здесь гирлянда «обтягивает» свою модель так, как
обтягивала стоковую: каждая точка провода и каждая лампочка встаёт на ту же
высоту над поверхностью, что была над стоковой

- Общее положение не угадывается: пушки ложатся в руку одинаково, а оценка
  сдвига и масштаба по двум разным формам врёт (совмещение поверхностей
  стягивало гирлянду ракетомёта к середине Direct Hit, хотя там она и так
  стояла). Берётся подгонка гирлянды, какую поставил человек, - без неё
  стоковая. Грубо сдвинул и растянул руками - обтянет уже оттуда.
- Высота - точное расстояние до треугольников своей модели со стороной по
  псевдонормалям (вершины, рёбра): у кромок тонкого клинка мера по
  ближайшей точке выборки путала сторону, и провод уходил внутрь.
- Недобор высоты штрафуется сильно, небольшой перелёт вверх - никак:
  провод - трубка, и кольцо, поставленное «в среднем», уходило низом в
  модель. Поправки сглаживаются вдоль самой гирлянды, а не по соседям в
  пространстве - иначе провод рвался бы на гранях.
- Тянется только то, что прилегало к стоковой и до чего своя поверхность
  недалеко: висевшее в воздухе едет за соседями, а не прыгает на чужую
  деталь.
- Итог - своя геометрия гирлянды (тот же SMD со сдвинутыми вершинами).
  Поверх неё работают подгонка и изгибы, как у любой гирлянды

Всё считается в bind-позе: в игре гирлянду, стоковую и свою модель двигают
одни и те же кости
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Dict, List, NamedTuple, Optional, Tuple

import numpy as np

from src.shared.logging_config import get_logger

logger = get_logger(__name__)

#: Выборка поверхности - подсказка, рядом с какими треугольниками точка, и
#: сколько ближайших точек выборки опрашивать: мерится уже по треугольникам
_DENSE = 16000
_CANDIDATES = 8
#: Прилегает ли точка (юниты): до первого порога - да, после второго - нет
_TOUCH_FULL = 2.5
_TOUCH_NONE = 6.0
#: Насколько провод может уйти в поверхность, как и у стоковой (юниты)
_CONTACT = 0.5
#: Длина сглаживания поправок вдоль провода и сколько раз уточнять высоту:
#: ближайшая точка поверхности меняется, пока гирлянда едет
_SMOOTH = 1.5
_ROUNDS = 12
#: Как далеко (юниты) ещё искать выход из вложенных деталей своей модели
_ESCAPE = 4.0
#: Когда высота считается выставленной (юниты)
_SETTLED = 0.01
#: Во сколько раз недобор высоты весит больше перелёта, и сколько перелёта
#: вверх не штрафуется вовсе (юниты): чуть выше - не видно, ниже - внутри
_BELOW = 4.0
_BAND = 0.12
#: Запас над нужной высотой у поднимаемых точек: погрешность изгибов (юниты)
_MARGIN = 0.04
#: К скольким точкам провода привязана лампочка
_BULB_LINKS = 3
#: Через сколько рёбер видно всё кольцо трубки провода (у кольца из шести
#: вершин противоположная - в трёх)
_RING_HOPS = 3
#: Пределы растяжения по длине: дальше это уже не та пушка, и гадать вредно
_STRETCH_MIN = 0.5
_STRETCH_MAX = 2.0
#: Насколько главная ось близка к оси модели (косинус), чтобы считать её ею
_AXIS_SNAP = 0.9


class AutofitError(ValueError):
    """Обтягивать не по чему: текст - для человека"""


@dataclass
class Result:
    """SMD обтянутой гирлянды; `report` - для журнала и тестов"""

    path: str
    report: Dict[str, float] = field(default_factory=dict)


# Поверхность

def read_triangles(path: str) -> Tuple[np.ndarray, np.ndarray]:
    """(позиции T×3×3, нормали T×3×3) треугольников SMD; пусто - не прочитано

    Треугольник - строка материала и три строки вершин; треугольник с
    нечитаемой вершиной пропускается целиком, а не сдвигает следующие
    """
    pos, nrm = [], []
    section = ''
    body: List[str] = []
    try:
        with open(path, encoding='utf-8', errors='replace') as f:
            for raw in f:
                low = raw.strip().lower()
                if low in ('nodes', 'skeleton', 'triangles', 'vertexanimation'):
                    section = low
                elif low == 'end':
                    section = ''
                elif section == 'triangles' and low:
                    body.append(raw)
    except OSError:
        body = []
    for i in range(0, len(body) - 3, 4):
        try:
            rows = [[float(v) for v in body[i + k].split()[1:7]] for k in (1, 2, 3)]
        except ValueError:
            continue
        # nan и inf в чужой модели сломали бы выборку поверхности
        if all(len(r) == 6 for r in rows) and all(map(math.isfinite, sum(rows, []))):
            pos.append([r[:3] for r in rows])
            nrm.append([r[3:] for r in rows])
    return (np.array(pos, np.float64).reshape(-1, 3, 3),
            np.array(nrm, np.float64).reshape(-1, 3, 3))


class Surface(NamedTuple):
    """Поверхность модели: выборка точек (чтобы быстро найти, рядом с какими
    треугольниками точка) и сами треугольники (чтобы мерить точно)"""

    pts: np.ndarray        # точки выборки, S×3
    nrm: np.ndarray        # нормали в них, наружу
    owner: np.ndarray      # треугольник каждой точки выборки
    tris: np.ndarray       # треугольники, T×3×3
    faces: np.ndarray      # нормали граней, наружу
    #: Псевдонормали углов (T×3×3) и рёбер (AB, BC, CA; T×3×3) - сумма
    #: граней, сходящихся в вершине (с весом по углу) или на ребре
    corner_n: np.ndarray
    edge_n: np.ndarray


def _pseudonormals(pos: np.ndarray, face: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
    """Псевдонормали вершин и рёбер (Bærentzen, Aanæs, 2005)

    Ближайшая точка на ребре или в вершине общая у нескольких граней, и
    сторона по одной из них врёт: у кромки клинка точка снаружи выходила
    «внутри» на 0,14. Сумма сходящихся граней (у вершины - с весом по углу)
    даёт верную сторону для любой замкнутой сетки
    """
    _, vid = np.unique(np.round(pos.reshape(-1, 3), 4), axis=0, return_inverse=True)
    vid = vid.reshape(-1, 3)
    corner = np.zeros((vid.max() + 1, 3))
    for k in range(3):
        e1 = pos[:, (k + 1) % 3] - pos[:, k]
        e2 = pos[:, (k + 2) % 3] - pos[:, k]
        cos = (e1 * e2).sum(1) / np.maximum(
            np.linalg.norm(e1, axis=1) * np.linalg.norm(e2, axis=1), 1e-12)
        np.add.at(corner, vid[:, k], face * np.arccos(np.clip(cos, -1, 1))[:, None])
    pairs = np.stack([np.sort(vid[:, [k, (k + 1) % 3]], axis=1) for k in range(3)], 1)
    _, eid = np.unique(pairs.reshape(-1, 2), axis=0, return_inverse=True)
    eid = eid.reshape(-1, 3)
    edge = np.zeros((eid.max() + 1, 3))
    for k in range(3):
        np.add.at(edge, eid[:, k], face)
    return corner[vid], edge[eid]


def _outward(pos: np.ndarray, nrm: np.ndarray, face: np.ndarray) -> np.ndarray:
    """Знак (±1) каждой грани, при котором она смотрит наружу

    Обход треугольников у модели из интернета надёжнее записанных нормалей:
    у ножа из GLB нормали смотрели внутрь при правильном обходе. Если обход
    согласован (знак объёма замкнутой сетки уверенный), верим ему; иначе -
    нормалям, а модель целиком выворачиваем по центру масс
    """
    rel = pos - pos.reshape(-1, 3).mean(0)
    vol = np.einsum('ij,ij->i', rel[:, 0], np.cross(rel[:, 1], rel[:, 2]))
    if abs(vol.sum()) > 0.1 * np.abs(vol).sum():
        return np.full(len(pos), 1.0 if vol.sum() > 0 else -1.0)
    stored = nrm.sum(1)
    sign = np.sign((stored * face).sum(1))
    sign[sign == 0] = 1.0
    if np.sum((pos.mean(1) - pos.reshape(-1, 3).mean(0)) * face * sign[:, None]) < 0:
        sign = -sign
    return sign


def sample(pos: np.ndarray, nrm: np.ndarray, count: int = _DENSE,
           seed: int = 0) -> Surface:
    """Поверхность: точки поровну на площадь и нормали в них, наружу"""
    a, b = pos[:, 1] - pos[:, 0], pos[:, 2] - pos[:, 0]
    cross = np.cross(a, b)
    area = np.linalg.norm(cross, axis=1)
    if not len(area) or area.sum() <= 0:
        empty = np.zeros((0, 3))
        return Surface(empty, empty, np.zeros(0, np.int64), pos, empty, pos, pos)
    face = cross / np.maximum(area, 1e-12)[:, None]
    face = face * _outward(pos, nrm, face)[:, None]
    corner_n, edge_n = _pseudonormals(pos, face)
    rng = np.random.default_rng(seed)
    pick = rng.choice(len(area), size=count, p=area / area.sum())
    u, v = rng.random(count), rng.random(count)
    flip = u + v > 1
    u[flip], v[flip] = 1 - u[flip], 1 - v[flip]
    pts = pos[pick, 0] + u[:, None] * a[pick] + v[:, None] * b[pick]
    n = ((1 - u - v)[:, None] * nrm[pick, 0] + u[:, None] * nrm[pick, 1]
         + v[:, None] * nrm[pick, 2])
    # Записанная нормаль - только сглаживание; сторону задаёт грань. Нет
    # записанной (модель без нормалей) - сама грань
    length = np.linalg.norm(n, axis=1)
    n = np.where(length[:, None] > 1e-6, n / np.maximum(length, 1e-12)[:, None], face[pick])
    n = n * np.where((n * face[pick]).sum(1) < 0, -1.0, 1.0)[:, None]
    return Surface(pts, n, pick, pos, face, corner_n, edge_n)


def _sq_dist(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    d = (a * a).sum(1)[:, None] - 2 * a @ b.T + (b * b).sum(1)[None, :]
    return np.maximum(d, 0.0)


def _nearest(query: np.ndarray, pts: np.ndarray, k: int = 1,
             chunk: int = 512) -> np.ndarray:
    """Номера `k` ближайших точек `pts` для каждой точки `query` (Q×k; при
    k=1 - вектор)"""
    # ponytail: перебор кусками, O(Q·P). Гирлянда - тысяча-другая точек,
    # выборка - десятки тысяч: доли секунды. Дерево - если вырастут
    k = min(k, len(pts))
    out = np.empty((len(query), k), np.int64)
    p32 = pts.astype(np.float32)
    for i in range(0, len(query), chunk):
        d2 = _sq_dist(query[i:i + chunk].astype(np.float32), p32)
        out[i:i + chunk] = (d2.argmin(1)[:, None] if k == 1
                            else np.argpartition(d2, k - 1, axis=1)[:, :k])
    return out[:, 0] if k == 1 else out


def _closest(p: np.ndarray, a: np.ndarray, b: np.ndarray,
             c: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
    """(ближайшая к p точка треугольника abc, где она) - массивами (Ericson,
    Real-Time Collision Detection, 5.1.5). Где: 0 - грань, 1-3 - вершина
    A/B/C, 4-6 - ребро AB/BC/CA"""
    ab, ac = b - a, c - a
    ap, bp, cp = p - a, p - b, p - c
    d1, d2 = (ab * ap).sum(1), (ac * ap).sum(1)
    d3, d4 = (ab * bp).sum(1), (ac * bp).sum(1)
    d5, d6 = (ab * cp).sum(1), (ac * cp).sum(1)
    va, vb, vc = d3 * d6 - d5 * d4, d5 * d2 - d1 * d6, d1 * d4 - d3 * d2
    with np.errstate(divide='ignore', invalid='ignore'):
        total = va + vb + vc
        out = a + ab * (vb / total)[:, None] + ac * (vc / total)[:, None]
        where = np.zeros(len(p), np.int64)
        # Области по убыванию: ставим с конца, первая подходящая - последней
        cases = [
            (va <= 0) & (d4 - d3 >= 0) & (d5 - d6 >= 0),
            (vb <= 0) & (d2 >= 0) & (d6 <= 0),
            (d6 >= 0) & (d5 <= d6),
            (vc <= 0) & (d1 >= 0) & (d3 <= 0),
            (d3 >= 0) & (d4 <= d3),
            (d1 <= 0) & (d2 <= 0),
        ]
        points = [
            b + (c - b) * ((d4 - d3) / ((d4 - d3) + (d5 - d6)))[:, None],
            a + ac * (d2 / (d2 - d6))[:, None],
            c,
            a + ab * (d1 / (d1 - d3))[:, None],
            b,
            a,
        ]
        for case, point, region in zip(cases, points, (5, 6, 3, 4, 2, 1)):
            out = np.where(case[:, None], point, out)
            where = np.where(case, region, where)
    # Вырожденный треугольник (все точки на прямой) - ближайшая вершина
    bad = ~np.isfinite(out).all(1)
    if bad.any():
        corners = np.stack([a[bad], b[bad], c[bad]], 1)
        pick = np.linalg.norm(corners - p[bad, None], axis=2).argmin(1)
        out[bad] = corners[np.arange(bad.sum()), pick]
        where[bad] = pick + 1
    return out, where


def height(points: np.ndarray, surface: Surface) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    """(высота над поверхностью, куда «наружу», расстояние) в ближайшей точке

    Мерится до самих треугольников рядом (их подсказывает выборка), а не до
    плоскости ближайшей точки выборки: у кромки та ошибалась до 0,05 и
    путала сторону, а на тонком клинке ножа кромки - везде. «Наружу» - от
    ближайшей точки к нашей: у кромки это вбок, вокруг неё, а не в грань.
    Сторона - по псевдонормали того места, где ближайшая точка
    """
    if not len(surface.pts):
        zero = np.zeros(len(points))
        return zero, np.zeros_like(points), np.full(len(points), np.inf)
    cand = surface.owner[_nearest(points, surface.pts, _CANDIDATES)]
    q, k = cand.shape
    tri = surface.tris[cand.reshape(-1)]
    near, where = _closest(np.repeat(points, k, axis=0), tri[:, 0], tri[:, 1], tri[:, 2])
    near, where = near.reshape(q, k, 3), where.reshape(q, k)
    dist = np.linalg.norm(points[:, None] - near, axis=2)
    best = dist.argmin(1)
    rows = np.arange(q)
    spot, gap, t, w = near[rows, best], dist[rows, best], cand[rows, best], where[rows, best]
    face = surface.faces[t].copy()
    at_corner = (w >= 1) & (w <= 3)
    face[at_corner] = surface.corner_n[t[at_corner], w[at_corner] - 1]
    on_edge = w >= 4
    face[on_edge] = surface.edge_n[t[on_edge], w[on_edge] - 4]
    face /= np.maximum(np.linalg.norm(face, axis=1), 1e-12)[:, None]
    vec = points - spot
    side = np.where((vec * face).sum(1) < 0, -1.0, 1.0)
    out = np.where(gap[:, None] > 1e-6,
                   vec / np.maximum(gap, 1e-12)[:, None] * side[:, None], face)
    return side * gap, out, gap


# Длина

def stretch(points: np.ndarray, stock: np.ndarray, own: np.ndarray,
            anchors: Optional[np.ndarray] = None) -> np.ndarray:
    """Точки, растянутые по осям пушки под размер своей модели

    Пушку держат за начало координат модели (кость оружия в руке), и в
    каждую сторону от него - вперёд и назад, вверх и вниз, влево и вправо -
    свой размер: короткий ствол сжимает гирлянду на стволе, модель, которую
    подгонкой сделали крупнее, растягивает её целиком (у минигана детали при
    этом уезжают вбок на юниты, и по одной высоте над поверхностью гирлянда
    за ними не успевала). Размер - по 1-99 % площади, чтобы тонкий штык или
    ремень не тянули гирлянду за собой. Лампочки размер не меняют: двигаются
    их центры

    `anchors` - где точка крепилась к стоковой (ближайшая точка её
    поверхности): растягивается крепление, а отступ от него переносится как
    есть - иначе вместе с пушкой рос бы и зазор до неё
    """
    base = points if anchors is None else anchors
    frame = np.linalg.svd(stock - stock.mean(0), full_matrices=False)[2]
    # Стоковые пушки выровнены по осям модели, а главную ось клонит лишняя
    # масса (ящик минигана - на 10°): растяжение по наклонной уводило
    # гирлянду вбок на три юнита
    if np.abs(frame[0]).max() > _AXIS_SNAP:
        frame = np.eye(3)
    out = points.copy()
    for axis in frame:
        us, uc = stock @ axis, own @ axis
        s0, s1 = np.percentile(us, [1, 99])
        c0, c1 = np.percentile(uc, [1, 99])
        # Хват вне пушки или у самого её края - тянуть с этой стороны нечего
        ahead = c1 / s1 if s1 > 1 and c1 > 1 else 1.0
        behind = c0 / s0 if s0 < -1 and c0 < -1 else 1.0
        u = base @ axis
        k = np.clip(np.where(u > 0, ahead, behind), _STRETCH_MIN, _STRETCH_MAX)
        out += ((k - 1) * u)[:, None] * axis
    return out


# Обтягивание

def _touch(dist: np.ndarray, scale: float) -> np.ndarray:
    """1 - лежит на поверхности, 0 - висит вдали; между - плавно"""
    lo, hi = _TOUCH_FULL * scale, _TOUCH_NONE * scale
    t = np.clip((hi - dist) / (hi - lo), 0.0, 1.0)
    return t * t * (3 - 2 * t)


def links(inverse: np.ndarray, groups: np.ndarray, corners: np.ndarray,
          centers: np.ndarray) -> np.ndarray:
    """Рёбра между единицами гирлянды (E×2): провод - по своим треугольникам,
    лампочка - к ближайшим точкам провода (она висит на нём, но вершин с
    ним не делит)"""
    tri = inverse.reshape(-1, 3)
    edges = np.concatenate([tri[:, [0, 1]], tri[:, [1, 2]], tri[:, [2, 0]]])
    edges = edges[edges[:, 0] != edges[:, 1]]
    bulb = np.zeros(len(centers), bool)
    bulb[inverse[groups >= 0]] = True
    wire = np.flatnonzero(~bulb)
    if len(wire):
        own = inverse[groups >= 0]
        verts = corners[groups >= 0]
        near = wire[_nearest(verts, centers[wire])]
        gap = np.linalg.norm(verts - centers[near], axis=1)
        extra = []
        for unit in np.unique(own):
            mine = np.flatnonzero(own == unit)
            closest = near[mine[np.argsort(gap[mine])]].tolist()
            extra += [(unit, k) for k in list(dict.fromkeys(closest))[:_BULB_LINKS]]
        if extra:
            edges = np.concatenate([edges, np.array(extra)])
    return np.unique(np.sort(edges, axis=1), axis=0)


def _spread(edges: np.ndarray, weight: np.ndarray, trust: np.ndarray,
            values: np.ndarray, iters: int = 400) -> np.ndarray:
    """Поправки, гладкие вдоль гирлянды: (доверие + связи) · x = доверие · values

    Сопряжённые градиенты по рёбрам. Точка без доверия (висит в воздухе)
    получает поправку соседей по проводу - плавно между теми, кто прилегает;
    провод не рвётся на гранях, а верх и низ тонкой детали не тянут друг
    друга - они соединены проводом только в обход
    """
    diag = trust + 1e-3
    a, b = edges[:, 0], edges[:, 1]
    n = len(values)

    def apply(x: np.ndarray) -> np.ndarray:
        flow = weight[:, None] * (x[a] - x[b])
        out = diag[:, None] * x
        for k in range(3):
            out[:, k] += (np.bincount(a, weights=flow[:, k], minlength=n)
                          - np.bincount(b, weights=flow[:, k], minlength=n))
        return out

    rhs = trust[:, None] * values
    x = np.zeros_like(values)
    r = rhs - apply(x)
    p = r.copy()
    rr = (r * r).sum(0)
    for _ in range(iters):
        if rr.max() <= 1e-10:
            break
        ap = apply(p)
        alpha = rr / np.maximum((p * ap).sum(0), 1e-30)
        x += alpha * p
        r -= alpha * ap
        rr_new = (r * r).sum(0)
        p = r + (rr_new / np.maximum(rr, 1e-30)) * p
        rr = rr_new
    return x


def wrap(points: np.ndarray, want: np.ndarray, attached: np.ndarray,
         own: tuple, edges: np.ndarray, scale: float = 1.0,
         rounds: int = _ROUNDS, outward: Optional[np.ndarray] = None) -> np.ndarray:
    """Точки на высоте `want` над своей поверхностью

    `attached` - насколько точка прилегала к стоковой (0..1). Тянется к
    своей поверхности только то, что прилегало и до чего она недалеко;
    уходящее под поверхность глубже, чем было на стоковой, выталкивается
    всегда. Поправки - гладкие вдоль гирлянды (`edges`, см. links)

    Ниже и выше нужного - не одно и то же. Провод - трубка, сглаживание
    двигает её кольцо целиком, и при равном штрафе кольцо вставало «в
    среднем»: сторона к поверхности уходила в модель (на тонком клинке ножа
    - 40 % провода). Поэтому недобор штрафуется сильно, небольшой перелёт
    вверх (`_BAND`) не штрафуется вовсе, а выше него - слабо
    """
    length = np.linalg.norm(points[edges[:, 0]] - points[edges[:, 1]], axis=1)
    weight = (_SMOOTH * scale) ** 2 / np.maximum(length, 0.2 * scale) ** 2
    floor = np.minimum(want, 0.0)
    band = _BAND * scale
    out = points.copy()
    # Куда выталкивают утонувшую точку. Направление держится, пока она не
    # выйдет: в тонком месте (между стволами двустволки, в щели между
    # вложенными деталями) ближайшая поверхность перескакивает на другую
    # сторону, и точку толкало бы туда-обратно, не выпуская. Начальное - та
    # сторона, с которой точка висела над стоковой (`outward`): ближайшая
    # стенка своей модели бывает внутренней, и у минигана ×1,3 провод
    # протаскивало между стволами на 2,7 юнита в сторону
    way = np.zeros_like(points)
    side = np.zeros_like(points) if outward is None else outward

    def measure():
        now, n, gap = height(out, own)
        sunk = now < floor
        held = sunk & (np.abs(way).sum(1) > 0)
        first = sunk & ~held & (np.abs(side).sum(1) > 0)
        n = np.where(held[:, None], way, np.where(first[:, None], side, n))
        way[:] = np.where(sunk[:, None], n, 0.0)
        return now, n, gap, sunk

    # Сглаживание съедает часть подъёма, и один проход его недобирает:
    # повторяем, пока что-то ниже нужного
    for _ in range(rounds):
        now, n, gap, sunk = measure()
        pull = attached * _touch(gap, scale)
        low = want - now
        # Поднимаемым - с запасом на погрешность изгибов: иначе её доли
        # хватило бы, чтобы край трубки снова ушёл в модель
        lift = np.where(low > _SETTLED * scale, low + _MARGIN * scale,
                        np.where(-low > band, low + band, 0.0))
        lift = np.where(pull > 0, lift, 0.0)
        lift = np.where(sunk & (lift < floor - now), floor - now, lift)
        trust = np.where(sunk, _BELOW, pull * np.where(low > 0, _BELOW, 1.0))
        trust = np.where(sunk | (lift != 0), trust, 0.0)
        if (lift[trust > 0].max(initial=0.0) <= _SETTLED * scale
                and lift[trust > 0].min(initial=0.0) >= -_SETTLED * 5 * scale):
            break
        out += _spread(edges, weight, trust, lift[:, None] * n)
    # Что за все проходы не дотянулось (у острых углов сглаживание сходится
    # медленно) - выталкиваем без сглаживания. Кольцо трубки провода - по
    # самой нуждающейся его точке и целиком: вытолкнутый поодиночке низ
    # кольца сплющил бы трубку, а такое изгибам не выразить (у ножа остаток
    # изгибов вырастал до 0,3)
    now, n, gap, _sunk = measure()
    need = np.maximum(np.where(attached * _touch(gap, scale) > 0, want, floor), floor) - now
    out += _widest(edges, np.where(need > 0, need + _MARGIN * scale, 0.0))[:, None] * n
    # Детали своей модели бывают вложены друг в друга (стволы двустволки
    # вставлены в коробку): вышедшая из одной точка оказывается в соседней.
    # Оставшиеся внутри выводим лучом по тому же направлению сразу за
    # последний слой. Уже без кольца: раздавай подъём соседям ещё раз, соседи
    # соседей уплывали бы вверх (у минигана - половина гирлянды)
    now, n, gap, sunk = measure()
    if sunk.any():
        idx = np.flatnonzero(sunk)
        step = _escape(out[idx], n[idx], own, _ESCAPE * scale)
        step = np.where(np.isfinite(step), step, (floor - now)[idx]) + _MARGIN * scale
        out[idx] += step[:, None] * n[idx]
    return out


def _escape(points: np.ndarray, dirs: np.ndarray, surface: Surface,
            limit: float) -> np.ndarray:
    """На сколько сдвинуть точку вдоль `dirs`, чтобы выйти из модели
    целиком; nan - не вышло (луч не пересёк, сетка открытая, выход дальше
    `limit`)

    Луч пересекает треугольники, и по ориентации каждого видно, вход это
    или выход. На бесконечности точка снаружи, поэтому, считая с дальнего
    конца, известно, на скольких деталях точка стоит после каждого
    пересечения, - первое, после которого ни на одной, и есть выход
    (Möller-Trumbore)
    """
    tri = surface.tris
    v0, e1, e2 = tri[:, 0], tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0]
    out = np.full(len(points), np.nan)
    for i in range(0, len(points), 16):
        p, d = points[i:i + 16], dirs[i:i + 16]
        h = np.cross(d[:, None, :], e2[None])
        a = (e1[None] * h).sum(2)
        ok = np.abs(a) > 1e-12
        f = np.where(ok, 1.0 / np.where(ok, a, 1.0), 0.0)
        s = p[:, None, :] - v0[None]
        u = f * (s * h).sum(2)
        q = np.cross(s, e1[None])
        v = f * (q * d[:, None, :]).sum(2)
        t = f * (q * e2[None]).sum(2)
        hit = ok & (u >= 0) & (u <= 1) & (v >= 0) & (u + v <= 1) & (t > 1e-6)
        leaving = (surface.faces[None] * d[:, None, :]).sum(2) > 0
        for row in range(len(p)):
            ts, ex = t[row][hit[row]], leaving[row][hit[row]]
            order = np.argsort(ts)
            ts, ex = ts[order], ex[order]
            delta = np.where(ex, -1, 1)
            after = -(np.cumsum(delta[::-1])[::-1] - delta)
            done = np.flatnonzero(ex & (after <= 0) & (ts <= limit))
            if len(done):
                out[i + row] = ts[done[0]]
    return out


def _widest(edges: np.ndarray, values: np.ndarray, hops: int = _RING_HOPS) -> np.ndarray:
    """Наибольшее значение среди соседей в `hops` рёбрах"""
    out = values.copy()
    a, b = edges[:, 0], edges[:, 1]
    for _ in range(hops):
        wider = out.copy()
        np.maximum.at(wider, a, out[b])
        np.maximum.at(wider, b, out[a])
        out = wider
    return out


# Всё вместе

def units(points: np.ndarray, groups: np.ndarray) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    """(центры, число вершин, номер единицы каждой вершины)

    Единица движения - жёсткая группа целиком (лампочка) или точка провода:
    у треугольников она повторяется, а двигается одинаково. Совпадение - как
    в festive_decor.rigid_groups
    """
    wire = np.round(points, 3)
    _, spot = np.unique(wire, axis=0, return_inverse=True)
    key = np.where(groups >= 0, groups, -1 - spot.reshape(-1))
    _, inverse = np.unique(key, return_inverse=True)
    inverse = inverse.reshape(-1)
    count = np.bincount(inverse).astype(np.float64)
    centers = np.stack([np.bincount(inverse, weights=points[:, k]) for k in range(3)], 1)
    return centers / count[:, None], count, inverse


def autofit(garland_smd: str, stock_smd: str, own_smd: str, out_path: str,
            fit: Optional[dict] = None) -> Result:
    """Гирлянда, обтянувшая свою модель так, как сидела на стоковой

    Пишет в `out_path` тот же SMD гирлянды со сдвинутыми вершинами: кости,
    веса, материалы, развёртка и порядок треугольников - как были, поэтому
    краска и части гирлянды остаются на месте. Изгибами это не выразить:
    провод по обе стороны тонкого клинка двигается врозь на сотые юнита, и
    у ножа их понадобились бы сотни при остатке в треть юнита
    (на минигане - три тысячи)

    `fit` - подгонка гирлянды: она остаётся как есть, вершины считаются под
    неё. Тот же вход - тот же ответ: выборки с одним зерном

    Raises:
        AutofitError: у какой-то из моделей не прочитались треугольники
        OSError: файл гирлянды не открылся или не записался
    """
    from src.services import festive_decor, mesh_import_service

    stock_pos, stock_nrm = read_triangles(stock_smd)
    own_pos, own_nrm = read_triangles(own_smd)
    if not len(stock_pos) or not len(own_pos):
        raise AutofitError('Нет треугольников у стоковой или своей модели')
    with open(garland_smd, encoding='utf-8', errors='replace') as f:
        lines, tris = festive_decor._smd_triangles(f.read())
    if not tris:
        raise AutofitError('Нет треугольников у гирлянды')
    corners = np.array([pt for tri in tris for pt in tri[2]], np.float64)
    groups = np.array(festive_decor.rigid_groups([tuple(p) for p in corners], len(tris)))

    shape = mesh_import_service.Fit.from_dict(fit)
    rot, s = np.array(shape.matrix()), shape.scale
    t = np.array(shape.offset, np.float64)

    start, _count, inverse = units(corners, groups)
    edges = links(inverse, groups, corners, start)
    stock = sample(stock_pos, stock_nrm)
    own = sample(own_pos, own_nrm)
    was, side_raw, dist = height(start, stock)
    shown = s * start @ rot.T + t
    touch = _touch(dist, 1.0)
    side = np.where(touch[:, None] > 0, side_raw @ rot.T, 0.0)
    # Подогнал руками - его положение главнее, растягивать не угадываем
    manual = shape != mesh_import_service.Fit()
    # Крепление - ближайшая точка стоковой; у висевшей в воздухе - она сама
    anchors = start - side_raw * (was * touch)[:, None]
    moved = shown if manual else stretch(start, stock[0], own[0], anchors)
    # Низ провода и на стоковой чуть уходит в поверхность - так и оставляем
    want = np.maximum(was, -_CONTACT) * s
    placed = wrap(moved, want, touch, own, edges, s, outward=side)
    # Подгонка применяется поверх файла: в файл - fit⁻¹(итог). Лампочка
    # едет целиком - сдвигом своего центра
    final = corners + ((((placed - t) / s) @ rot) - start)[inverse]

    rows = [row for tri in tris for row in tri[1]]
    for row, pt in zip(rows, final.tolist()):
        parts = lines[row].split()
        parts[1:4] = [f'{v:.6f}' for v in pt]
        lines[row] = ' '.join(parts)
    with open(out_path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines))

    before, _n, _d = height(shown, own)
    after, _n, _d = height(placed, own)
    report = {'moved': float(np.linalg.norm(placed - shown, axis=1).max()),
              'sunk_before': float((before < -0.01).mean()),
              'sunk_after': float((after < -0.01).mean())}
    logger.info(f"[автоподгонка] сдвиг до {report['moved']:.2f}, утоплено "
                f"{report['sunk_before']:.0%} -> {report['sunk_after']:.0%}")
    return Result(path=out_path, report=report)
