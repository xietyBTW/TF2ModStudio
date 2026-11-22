"""
Своя модель на место оригинала одним щелчком: размер, поворот и сдвиг

Модель «из интернета» приходит как попало: на боку, стволом не туда, в 100
раз больше (метры против юнитов Source), а бывает и под произвольным углом.
Вручную по призраку это самый муторный шаг, здесь он делается за человека -
потом остаётся подправить.

Как:
1. Кандидаты поворота: 24 на прямые углы (другая ось вверх, ствол вдоль другой
   оси) и положения по главным осям формы - они не зависят от того, как
   модель повернули, - с доворотами вокруг длинной оси: у круглого в сечении
   (бутылка, ствол) две короткие оси главными не определяются.
2. Каждый кандидат вписывается по центру масс и размаху точек и грубо
   оценивается на немногих точках.
3. Лучшие несколько доводятся (ICP с масштабом), и побеждает тот, что после
   доводки ближе к оригиналу. Выбирать до доводки нельзя: на наклонённой или
   непохожей модели развёрнутый задом наперёд вариант по прикидке бывал чуть
   лучше, и доводка сходилась не туда (катана изгибом в другую сторону).
4. В доводке пары берутся в обе стороны, самые далёкие не участвуют: торчащий
   штык или прицел не тянут модель за собой.

Только numpy: точек по паре сотен-тысяч, расстояния - матрицей
"""

from __future__ import annotations

import itertools
import math
from typing import List, Tuple

import numpy as np

from src.services.mesh_import_service import Fit, _euler_xyz

#: Точек на грубую оценку кандидатов, на их короткую доводку, на доводку
#: победителя и на последнюю
_COARSE, _SHORT, _MEDIUM, _FINE = 300, 450, 800, 1500
#: Сколько лучших кандидатов доводить и сколькими шагами: коротко всех, до
#: конца - только победителя (иначе подгонка шла секунды)
_TOP = 6
_SHORT_STEPS, _ICP_STEPS, _FINE_STEPS = 10, 25, 4
#: Доля ближайших пар, по которым считается доводка
_KEEP = 0.85
#: Доводка не уводит масштаб дальше этого от начального
_SCALE_DRIFT = 1.5
#: Доворотов вокруг длинной оси у кандидатов по главным осям
_SPINS = 12

Rigid = Tuple[np.ndarray, float, np.ndarray]


def _axis_rotations() -> List[np.ndarray]:
    """24 поворота на прямые углы: перестановки осей со знаками, без зеркал"""
    out = []
    for perm in itertools.permutations(range(3)):
        for signs in itertools.product((1.0, -1.0), repeat=3):
            m = np.zeros((3, 3))
            for row, (col, sign) in enumerate(zip(perm, signs)):
                m[row, col] = sign
            if np.linalg.det(m) > 0:
                out.append(m)
    return out


_AXIS_ROTATIONS = _axis_rotations()


def _sample(points: np.ndarray, count: int) -> np.ndarray:
    """Не больше `count` точек; выбор повторяемый - одна модель, один ответ"""
    if len(points) <= count:
        return points
    return points[np.random.default_rng(0).choice(len(points), count, replace=False)]


def _surface(corners: np.ndarray, count: int) -> np.ndarray:
    """
    Точки равномерно по поверхности: треугольник выбирается по площади,
    точка в нём - случайная

    Вершины для этого не годятся: их тысячи там, где мелкая деталь
    (механизм, курок), и единицы на гладком стволе. Совпадение тогда
    считалось по тому, где у моделей больше мелочи, а не по форме, и у
    похожих, но разных моделей побеждал перевёрнутый поворот
    """
    tri = corners[: len(corners) // 3 * 3].reshape(-1, 3, 3)
    area = np.linalg.norm(np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0]), axis=1)
    if not len(tri) or area.sum() <= 0:
        return _sample(corners, count)
    rng = np.random.default_rng(0)
    pick = rng.choice(len(tri), count, p=area / area.sum())
    u, v = rng.random(count), rng.random(count)
    flip = u + v > 1
    u[flip], v[flip] = 1 - u[flip], 1 - v[flip]
    t = tri[pick]
    return t[:, 0] + u[:, None] * (t[:, 1] - t[:, 0]) + v[:, None] * (t[:, 2] - t[:, 0])


def _nearest(a: np.ndarray, b: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
    """Для каждой точки a - номер ближайшей в b и расстояние до неё"""
    d2 = (a * a).sum(1)[:, None] + (b * b).sum(1)[None, :] - 2.0 * a @ b.T
    idx = d2.argmin(1)
    return idx, np.sqrt(np.maximum(d2[np.arange(len(a)), idx], 0.0))


def _trimmed(dist: np.ndarray) -> float:
    """Среднее по ближайшим _KEEP: лишние детали не решают за всю модель"""
    return float(np.sort(dist)[:max(1, int(len(dist) * _KEEP))].mean())


def _cost(a: np.ndarray, b: np.ndarray) -> float:
    """Насколько точки a и b не совпадают - в обе стороны"""
    return _trimmed(_nearest(a, b)[1]) + _trimmed(_nearest(b, a)[1])


def _apply(points: np.ndarray, fit: Rigid) -> np.ndarray:
    rot, scale, offset = fit
    return scale * points @ rot.T + offset


def _spread(points: np.ndarray) -> float:
    return float(np.sqrt(((points - points.mean(0)) ** 2).sum(1).mean()))


def _place(src: np.ndarray, dst: np.ndarray, rot: np.ndarray) -> Rigid:
    """Масштаб и сдвиг к повороту: центр масс к центру, размах к размаху -
    не зависят от поворота, в отличие от габаритов"""
    scale = _spread(dst) / max(_spread(src), 1e-9)
    return rot, scale, dst.mean(0) - scale * rot @ src.mean(0)


def _principal(points: np.ndarray) -> np.ndarray:
    """Главные оси (столбцы): от длинной к короткой, правая тройка"""
    vals, vecs = np.linalg.eigh(np.cov((points - points.mean(0)).T))
    vecs = vecs[:, np.argsort(vals)[::-1]]
    if np.linalg.det(vecs) < 0:
        vecs[:, 2] *= -1
    return vecs


def _spin(axis: np.ndarray, angle: float) -> np.ndarray:
    """Поворот на `angle` вокруг единичной оси"""
    k = np.array([[0, -axis[2], axis[1]], [axis[2], 0, -axis[0]], [-axis[1], axis[0], 0]])
    return np.eye(3) + math.sin(angle) * k + (1 - math.cos(angle)) * k @ k


def _candidates(src: np.ndarray, dst: np.ndarray) -> List[np.ndarray]:
    """Повороты, с которых стоит начинать: прямые углы и главные оси"""
    ps, pd = _principal(src), _principal(dst)
    out = list(_AXIS_ROTATIONS)
    for sx, sy in itertools.product((1.0, -1.0), repeat=2):
        flip = np.diag([sx, sy, sx * sy])               # без зеркал
        base = pd @ flip @ ps.T
        for k in range(_SPINS):
            out.append(_spin(pd[:, 0], 2 * math.pi * k / _SPINS) @ base)
    return out


def _umeyama(a: np.ndarray, b: np.ndarray) -> Rigid:
    """Поворот, масштаб и сдвиг, лучше всего переводящие a в b (по парам)"""
    mu_a, mu_b = a.mean(0), b.mean(0)
    da, db = a - mu_a, b - mu_b
    u, d, vt = np.linalg.svd(db.T @ da / len(a))
    s = np.eye(3)
    if np.linalg.det(u) * np.linalg.det(vt) < 0:
        s[2, 2] = -1.0
    rot = u @ s @ vt
    var_a = float((da * da).sum()) / len(a)
    scale = float(np.trace(np.diag(d) @ s)) / var_a if var_a > 1e-12 else 1.0
    return rot, scale, mu_b - scale * rot @ mu_a


def _refine(src: np.ndarray, dst: np.ndarray, fit: Rigid, steps: int) -> Tuple[float, Rigid]:
    """Доводка по ближайшим точкам в обе стороны. Хуже, чем было, - не берём"""
    best = (_cost(_apply(src, fit), dst), fit)
    base = fit[1]
    for _ in range(steps):
        moved = _apply(src, fit)
        i_ab, d_ab = _nearest(moved, dst)
        i_ba, d_ba = _nearest(dst, moved)
        keep_ab = d_ab <= np.quantile(d_ab, _KEEP)
        keep_ba = d_ba <= np.quantile(d_ba, _KEEP)
        a = np.vstack([src[keep_ab], src[i_ba[keep_ba]]])
        b = np.vstack([dst[i_ab[keep_ab]], dst[keep_ba]])
        if len(a) < 3:
            break
        fit = _umeyama(a, b)
        if not base / _SCALE_DRIFT <= fit[1] <= base * _SCALE_DRIFT:
            break
        cost = _cost(_apply(src, fit), dst)
        if cost < best[0] - 1e-9:
            best = (cost, fit)
        elif cost > best[0] * 1.001:
            break
    return best


def _distinct(fits: List[Tuple[float, Rigid]], count: int) -> List[Rigid]:
    """Лучшие `count` кандидатов, не повторяющие друг друга (поворот ближе
    15° к уже взятому - тот же кандидат)"""
    out: List[Rigid] = []
    for _, fit in sorted(fits, key=lambda f: f[0]):
        if all(np.trace(fit[0] @ o[0].T) < 1 + 2 * math.cos(math.radians(15)) for o in out):
            out.append(fit)
        if len(out) == count:
            break
    return out


def fit_to(points: np.ndarray, target: np.ndarray) -> Fit:
    """
    Подгонка точек своей модели (оси SMD оружия, без подгонки) к точкам
    оригинала - в тех же числах, что крутит человек (Fit)
    """
    points = np.asarray(points, np.float64).reshape(-1, 3)
    target = np.asarray(target, np.float64).reshape(-1, 3)
    if len(points) < 4 or len(target) < 4:
        return Fit()
    # Вершины идут тройками треугольников (SMD, импорт) - по ним точки
    # кладутся равномерно на поверхность; дальше работаем только с ними
    points = _surface(points, _FINE * 2)
    target = _surface(target, _FINE * 2)
    coarse_s, coarse_d = _sample(points, _COARSE), _sample(target, _COARSE)
    short_s, short_d = _sample(points, _SHORT), _sample(target, _SHORT)
    mid_s, mid_d = _sample(points, _MEDIUM), _sample(target, _MEDIUM)

    scored = []
    for rot in _candidates(mid_s, mid_d):
        fit = _place(mid_s, mid_d, rot)
        scored.append((_cost(_apply(coarse_s, fit), coarse_d), fit))
    refined = [_refine(short_s, short_d, fit, _SHORT_STEPS) for fit in _distinct(scored, _TOP)]
    _, best = min(refined, key=lambda r: r[0])
    _, best = _refine(mid_s, mid_d, best, _ICP_STEPS)
    _, (rot, scale, offset) = _refine(_sample(points, _FINE), _sample(target, _FINE),
                                      best, _FINE_STEPS)
    # Числа видит человек в полях подгонки: -90.000005 вместо -90 - шум
    # доводки, а не точность
    return Fit(scale=round(float(scale), 4),
               rotate=tuple(round(a, 2) + 0.0 for a in _euler_xyz(rot)),
               offset=tuple(round(float(v), 3) for v in offset))
