"""Автоподгонка своей модели к оригиналу: поворот, масштаб и сдвиг

Модели - настоящие треугольники (вершины тройками, как в SMD и импорте):
подгонка раскладывает точки по их площади
"""

import math
import unittest

import numpy as np

from src.services.auto_fit import fit_to
from src.services.mesh_import_service import Fit

_FACES = [(0, 1, 3), (0, 3, 2), (4, 6, 7), (4, 7, 5), (0, 4, 5), (0, 5, 1),
          (2, 3, 7), (2, 7, 6), (0, 2, 6), (0, 6, 4), (1, 5, 7), (1, 7, 3)]


def _box(lo, hi, cuts=6):
    """Коробка треугольниками; длинные грани порезаны, чтобы изгиб был виден"""
    lo, hi = np.array(lo, float), np.array(hi, float)
    long_ax = int(np.argmax(hi - lo))
    out = []
    for k in range(cuts):
        a, b = lo.copy(), hi.copy()
        a[long_ax] = lo[long_ax] + (hi - lo)[long_ax] * k / cuts
        b[long_ax] = lo[long_ax] + (hi - lo)[long_ax] * (k + 1) / cuts
        v = np.array([[x, y, z] for x in (a[0], b[0]) for y in (a[1], b[1]) for z in (a[2], b[2])])
        out.extend(v[list(f)] for f in _FACES)
    return np.vstack(out)


def _gun():
    """Несимметричный «пистолет»: ствол вдоль +Z, рукоять вниз у казны,
    мушка сверху у дула - так дуло не спутать с прикладом, а верх с низом"""
    return np.vstack([_box((-1, -1, 0), (1, 1, 20)),
                      _box((-1, -9, 0), (1, -1, 4)),
                      _box((-0.4, 1, 18), (0.4, 2.5, 19.5))])


def _katana(bend=2.5):
    """Клинок вдоль +Y, изогнут к +X; рукоять у основания и гарда"""
    blade = _box((-0.2, 0, -1), (0.2, 30, 1), cuts=12)
    t = blade[:, 1] / 30
    blade[:, 0] += bend * t * t
    return np.vstack([blade, _box((-0.5, -8, -0.8), (0.5, 0, 0.8)),
                      _box((-1.5, -0.3, -1.5), (1.5, 0.3, 1.5))])


def _place(points, fit: Fit):
    return points @ np.array(fit.matrix()).T * fit.scale + np.array(fit.offset)


def _move(points, wrong: Fit):
    """Модель «из интернета»: оригинал, развёрнутый и растянутый как попало"""
    inv = np.linalg.inv(np.array(wrong.matrix()))
    return (points - np.array(wrong.offset)) @ inv.T / wrong.scale


def _gap(a, b):
    """Среднее расстояние от точек a до ближайших в b"""
    d2 = (a * a).sum(1)[:, None] + (b * b).sum(1)[None, :] - 2 * a @ b.T
    return float(np.sqrt(np.maximum(d2.min(1), 0)).mean())


def _angle(a: Fit, b: Fit) -> float:
    m = np.array(a.matrix()) @ np.array(b.matrix()).T
    return math.degrees(math.acos(max(-1.0, min(1.0, (np.trace(m) - 1) / 2))))


class AutoFitTests(unittest.TestCase):
    def _check(self, target, wrong: Fit):
        mine = _move(target, wrong)
        fit = fit_to(mine, target)
        size = float(np.ptp(target, 0).max())
        self.assertLess(_gap(_place(mine, fit), target), size * 0.02, fit)
        self.assertLess(_angle(fit, wrong), 5.0, fit)
        return fit

    def test_lying_on_side_and_backwards_in_meters(self):
        wrong = Fit(scale=1 / 39.37, rotate=(90.0, 180.0, 0.0), offset=(5.0, -3.0, 40.0))
        fit = self._check(_gun(), wrong)
        self.assertAlmostEqual(fit.scale, wrong.scale, delta=wrong.scale * 0.03)

    def test_y_up_export(self):
        self._check(_gun(), Fit(scale=2.5, rotate=(-90.0, 0.0, 90.0)))

    def test_arbitrary_angle(self):
        # Не прямой угол вовсе: кандидаты по главным осям формы
        self._check(_gun(), Fit(scale=1.0, rotate=(37.0, -52.0, 118.0), offset=(1.0, 2.0, 3.0)))

    def test_curved_blade_keeps_its_bend(self):
        # Катана: изгиб клинка решает, какой стороной её ставить
        self._check(_katana(), Fit(scale=0.5, rotate=(0.0, 180.0, 90.0), offset=(4.0, 0.0, 0.0)))

    def test_other_sculpt_of_the_same_weapon(self):
        # Своя катана: клинок длиннее и изогнут сильнее, рукоять толще
        mine = _katana(bend=4.0) * np.array([1.2, 1.15, 0.9])
        wrong = Fit(scale=3.0, rotate=(90.0, 0.0, 180.0), offset=(0.0, 5.0, 0.0))
        fit = fit_to(_move(mine, wrong), _katana())
        self.assertLess(_angle(fit, wrong), 15.0, fit)

    def test_protruding_part_does_not_wreck_the_fit(self):
        # Свой ствол со штыком: лишняя деталь, которой у оригинала нет
        target = _gun()
        mine = np.vstack([target, _box((-0.3, -0.5, 20), (0.3, 0.5, 27))])
        fit = fit_to(mine, target)
        self.assertLess(_gap(_place(target, fit), target), 1.0)

    def test_degenerate_input_keeps_identity(self):
        self.assertEqual(fit_to(np.zeros((0, 3)), _gun()), Fit())
        self.assertTrue(math.isfinite(fit_to(_gun()[:6], _gun()).scale))


if __name__ == "__main__":
    unittest.main()
