"""Автоподгонка гирлянды: на своей модели она сидит так же, как на стоковой

Модели синтетические: «пушка» - цилиндр вдоль X, гирлянда - спираль-трубка
вокруг него с лампочками-кубиками. Проверяется итог, который увидит игра:
обтянутый SMD гирлянды (с подгонкой - через festive_decor.shaped_smd)
"""

import math
from pathlib import Path

import numpy as np
import pytest

from src.services import decor_autofit as da
from src.services import festive_decor
from src.services.mesh_import_service import smd_points


def _write_smd(path, tris):
    """tris: [(материал, [(точка, нормаль) ×3])]"""
    rows = ["version 1", "nodes", '0 "root" -1', "end", "skeleton", "time 0",
            "0 0 0 0 0 0 0", "end", "triangles"]
    for mat, corners in tris:
        rows.append(mat)
        for p, n in corners:
            rows.append("0 " + " ".join(f"{v:.6f}" for v in (*p, *n)) + " 0 0 1 0 1")
    rows.append("end")
    Path(path).write_text("\n".join(rows) + "\n", encoding="utf-8")
    return str(path)


def _quad(a, b, c, d, n=None):
    """Два треугольника a-b-c, a-c-d; нормаль - своя у каждой вершины или общая"""
    na, nb, nc, nd = n if n is not None else [np.cross(b - a, c - a)] * 4
    return [[(a, na), (b, nb), (c, nc)], [(a, na), (c, nc), (d, nd)]]


def _cylinder(radius, x0, x1, seg=32, rings=40):
    """Закрытый цилиндр вдоль X, нормали наружу"""
    tris = []
    xs = np.linspace(x0, x1, rings + 1)
    ang = np.linspace(0, 2 * math.pi, seg + 1)
    ring = lambda x, a: np.array([x, radius * math.cos(a), radius * math.sin(a)])  # noqa: E731
    out = lambda a: np.array([0, math.cos(a), math.sin(a)])                        # noqa: E731
    for i in range(rings):
        for j in range(seg):
            a0, a1 = ang[j], ang[j + 1]
            tris += _quad(ring(xs[i], a0), ring(xs[i + 1], a0), ring(xs[i + 1], a1),
                          ring(xs[i], a1), [out(a0), out(a0), out(a1), out(a1)])
    for x, sign in ((x0, -1.0), (x1, 1.0)):
        c = np.array([x, 0, 0])
        for j in range(seg):
            a, b = ring(x, ang[j]), ring(x, ang[j + 1])
            n = np.array([sign, 0, 0])
            tris.append([(c, n), (a, n), (b, n)] if sign > 0 else [(c, n), (b, n), (a, n)])
    return [("gun", t) for t in tris]


def _garland(radius, x0, x1, turns=3, tube=0.2, bulbs=6):
    """Спираль-провод вокруг оси X и лампочки-кубики на ней"""
    tris = []
    steps = 160
    ts = np.linspace(0, 1, steps + 1)
    center = lambda t: np.array([x0 + (x1 - x0) * t,                               # noqa: E731
                                 radius * math.cos(2 * math.pi * turns * t),
                                 radius * math.sin(2 * math.pi * turns * t)])
    rings = []
    for t in ts:
        c = center(t)
        radial = np.array([0, c[1], c[2]]) / radius
        side = np.cross(center(min(t + 1e-3, 1)) - center(max(t - 1e-3, 0)), radial)
        side /= np.linalg.norm(side)
        rings.append([c + tube * (math.cos(a) * radial + math.sin(a) * side)
                      for a in np.linspace(0, 2 * math.pi, 7)[:-1]])
    for i in range(steps):
        for j in range(6):
            a, b = rings[i][j], rings[i + 1][j]
            c, d = rings[i + 1][(j + 1) % 6], rings[i][(j + 1) % 6]
            tris += _quad(a, b, c, d)
    for k in range(bulbs):
        c = center((k + 0.5) / bulbs)
        radial = np.array([0, c[1], c[2]]) / radius
        base = c + radial * (tube + 0.35)
        h = 0.3
        corner = [base + np.array(o) * h for o in
                  [(-1, -1, -1), (1, -1, -1), (1, 1, -1), (-1, 1, -1),
                   (-1, -1, 1), (1, -1, 1), (1, 1, 1), (-1, 1, 1)]]
        for q in [(0, 1, 2, 3), (4, 7, 6, 5), (0, 4, 5, 1), (1, 5, 6, 2), (2, 6, 7, 3), (3, 7, 4, 0)]:
            tris += _quad(*(corner[i] for i in q))
    return [("lights", t) for t in tris]


def _box(half):
    """Коробка с центром в начале координат, нормали граней наружу"""
    tris = []
    for axis in range(3):
        for sign in (-1.0, 1.0):
            n = np.zeros(3)
            n[axis] = sign
            u, v = [k for k in range(3) if k != axis]
            corner = []
            for a, b in ((-1, -1), (1, -1), (1, 1), (-1, 1)):
                p = np.zeros(3)
                p[axis] = sign * half[axis]
                p[u], p[v] = a * half[u], b * half[v]
                corner.append(p)
            if np.dot(np.cross(corner[1] - corner[0], corner[2] - corner[0]), n) < 0:
                corner.reverse()
            tris += [[(c, n) for c in t] for t in
                     ([corner[0], corner[1], corner[2]], [corner[0], corner[2], corner[3]])]
    return [("gun", t) for t in tris]


def _wrapped_wire(half, gap, tube=0.08, turns=6, steps=240):
    """Провод, плотно обвивающий коробку по оси X на зазоре `gap`"""
    def around(t):
        a = 2 * math.pi * turns * t
        c, s = math.cos(a), math.sin(a)
        # Точка на контуре сечения (прямоугольник), сдвинутая наружу
        k = min(half[1] / max(abs(c), 1e-9), half[2] / max(abs(s), 1e-9))
        y, z = c * k, s * k
        ny = np.sign(y) if abs(abs(y) - half[1]) < 1e-6 else 0.0
        nz = np.sign(z) if abs(abs(z) - half[2]) < 1e-6 else 0.0
        n = np.array([0.0, ny, nz])
        n /= np.linalg.norm(n)
        x = -half[0] * 0.8 + 1.6 * half[0] * t
        return np.array([x, y, z]) + n * (gap + tube)
    rings = []
    for t in np.linspace(0, 1, steps + 1):
        c = around(t)
        ahead = around(min(t + 1e-3, 1)) - around(max(t - 1e-3, 0))
        ahead /= np.linalg.norm(ahead)
        side = np.cross(ahead, [1.0, 0, 0])
        side = side / np.linalg.norm(side) if np.linalg.norm(side) > 1e-6 else np.array([0, 1.0, 0])
        up = np.cross(ahead, side)
        rings.append([c + tube * (math.cos(a) * side + math.sin(a) * up)
                      for a in np.linspace(0, 2 * math.pi, 7)[:-1]])
    tris = []
    for i in range(steps):
        for j in range(6):
            tris += _quad(rings[i][j], rings[i + 1][j], rings[i + 1][(j + 1) % 6],
                          rings[i][(j + 1) % 6])
    return [("lights", t) for t in tris]


@pytest.mark.parametrize("grow", [1.05, 1.2, 1.5])
def test_wire_tight_on_a_thin_blade_stays_outside_a_bigger_one(tmp_path, grow):
    # Нож: провод обвивает тонкий клинок вплотную. Своя модель больше всего
    # на 5-50 % - и провод не должен уйти внутрь ни одной вершиной
    blade = np.array([10.0, 1.2, 0.35])
    stock = _write_smd(tmp_path / "stock.smd", _box(blade))
    garland = _write_smd(tmp_path / "garland.smd", _wrapped_wire(blade, 0.03))
    own = _write_smd(tmp_path / "own.smd", _box(blade * [1.0, grow, grow]))
    big = blade * [1.0, grow, grow]

    def depth(points, box):
        """Насколько вершина внутри коробки (<= 0 - снаружи)"""
        return (box - np.abs(points)).min(axis=1)

    # На стоковой провод весь снаружи - и на своей внутрь нельзя ни вершиной
    assert depth(smd_points(garland), blade).max() < 0
    assert depth(smd_points(garland), big).max() > 0
    res = da.autofit(garland, stock, own, str(tmp_path / "w.smd"))
    assert depth(smd_points(res.path), big).max() < 0


@pytest.fixture
def models(tmp_path):
    stock = _write_smd(tmp_path / "stock.smd", _cylinder(2.0, -5, 20))
    garland = _write_smd(tmp_path / "garland.smd", _garland(2.6, 0, 15))
    return tmp_path, stock, garland


def _heights(points, smd):
    return da.height(points, da.sample(*da.read_triangles(smd), count=8000))[0]


def test_own_same_as_stock_changes_nothing(models):
    tmp, stock, garland = models
    res = da.autofit(garland, stock, stock, str(tmp / "w.smd"))
    assert np.abs(smd_points(res.path) - smd_points(garland)).max() < 1e-5


def test_thicker_model_lifts_the_lights_to_the_same_height(models):
    tmp, stock, garland = models
    own = _write_smd(tmp / "own.smd", _cylinder(3.0, -5, 20))
    before = smd_points(garland)
    after = smd_points(da.autofit(garland, stock, own, str(tmp / "w.smd")).path)

    want = _heights(before, stock)
    got = _heights(after, own)
    # Без подгонки гирлянда утонула бы в толстом цилиндре целиком
    assert (_heights(before, own) < 0).mean() > 0.9
    assert np.median(np.abs(got - want)) < 0.1
    assert got.min() > -0.5


def test_thinner_model_pulls_the_lights_down(models):
    tmp, stock, garland = models
    own = _write_smd(tmp / "own.smd", _cylinder(1.3, -5, 20))
    before = smd_points(garland)
    got = _heights(smd_points(da.autofit(garland, stock, own, str(tmp / "w.smd")).path), own)
    want = _heights(before, stock)
    # Опускается до высоты на стоковой; чуть выше - допустимо, ниже - нет
    assert np.median(got - want) == pytest.approx(0.1, abs=0.1)
    assert (got - want).min() > -0.05


def test_shorter_gun_keeps_the_lights_on_it(models):
    # Ствол на треть короче: гирлянда не висит за дулом в воздухе
    tmp, stock, garland = models
    own = _write_smd(tmp / "own.smd", _cylinder(2.0, -5, 12))
    after = smd_points(da.autofit(garland, stock, own, str(tmp / "w.smd")).path)
    assert smd_points(garland)[:, 0].max() > 14
    assert after[:, 0].max() < 12.5


def test_manual_fit_is_kept_and_wins_over_stretch(models):
    # Человек сам растянул гирлянду: длину не угадываем, изгибы - под его
    # подгонку, и в итоге гирлянда всё равно на поверхности
    tmp, stock, garland = models
    own = _write_smd(tmp / "own.smd", _cylinder(2.6, -5, 20))
    fit = {"scale": 1.1, "rotate": [0, 0, 0], "offset": [0.5, 0, 0]}
    res = da.autofit(garland, stock, own, str(tmp / "w.smd"), fit)
    after = smd_points(festive_decor.shaped_smd(res.path, fit, []))
    got = _heights(after, own)
    assert np.median(got) == pytest.approx(np.median(_heights(smd_points(garland), stock)) * 1.1,
                                           abs=0.15)
    assert got.min() > -0.6


def test_only_positions_change(models):
    # Краска и части гирлянды держатся за треугольники и развёртку: обтянутый
    # SMD обязан совпасть с исходным во всём, кроме позиций вершин
    tmp, stock, garland = models
    own = _write_smd(tmp / "own.smd", _cylinder(3.0, -5, 20))
    res = da.autofit(garland, stock, own, str(tmp / "w.smd"))
    src = Path(garland).read_text(encoding="utf-8").splitlines()
    got = Path(res.path).read_text(encoding="utf-8").splitlines()
    assert len(src) == len(got)
    moved = 0
    for a, b in zip(src, got):
        pa, pb = a.split(), b.split()
        if len(pa) >= 9 and pa[0].isdigit():
            assert pa[0] == pb[0] and pa[4:] == pb[4:]
            moved += pa[1:4] != pb[1:4]
        else:
            assert a == b
    assert moved


def test_broken_vertex_drops_its_triangle_only(tmp_path):
    path = tmp_path / "m.smd"
    good = "0 0 0 0 0 0 1 0 0 1 0 1"
    path.write_text("\n".join(["version 1", "triangles",
                               "m", good, good, good,
                               "m", good, "0 nan? 0 0 0 0 1 0 0", good,
                               "m", good, "0 inf 0 0 0 0 1 0 0 1 0 1", good,
                               "m", good, good, "0 5 5 5 0 0 1 0 0 1 0 1",
                               "end"]), encoding="utf-8")
    pos, _nrm = da.read_triangles(str(path))
    assert len(pos) == 2
    assert pos[1][2].tolist() == [5.0, 5.0, 5.0]
