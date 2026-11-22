"""
Габариты OBJ - от них зависит, попадёт модель в кадр или уедет за него

Считаются в Python намеренно: bounding box у Three.js сразу после загрузки
ненадёжен. Этим правилом пользуются и виджет превью, и веб-фронт
"""

import unittest

from src.domain.preview.obj_bounds import TARGET_EXTENT, compute_obj_bounds


def _cube(size: float, offset=(0.0, 0.0, 0.0)) -> str:
    ox, oy, oz = offset
    h = size / 2
    pts = [(x, y, z) for x in (-h, h) for y in (-h, h) for z in (-h, h)]
    return "\n".join(f"v {x + ox} {y + oy} {z + oz}" for x, y, z in pts)


class ObjBoundsTests(unittest.TestCase):
    def test_centre_of_a_shifted_cube(self):
        cx, cy, cz, _ = compute_obj_bounds(_cube(2.0, offset=(10.0, -4.0, 3.0)))
        self.assertAlmostEqual(cx, 10.0)
        self.assertAlmostEqual(cy, -4.0)
        self.assertAlmostEqual(cz, 3.0)

    def test_scale_fits_the_longest_side(self):
        """Масштаб считается по наибольшей стороне, иначе модель вылезет из кадра"""
        obj = "v 0 0 0\nv 8 1 1"          # длина по X - 8
        _, _, _, scale = compute_obj_bounds(obj)
        self.assertAlmostEqual(scale, TARGET_EXTENT / 8)

    def test_empty_and_broken_input_is_safe(self):
        """Пустой или битый OBJ не должен ронять загрузку - показывать всё равно нечего"""
        for obj in ("", "# только комментарий", "v ещё не число", "v 1 2"):
            self.assertEqual(compute_obj_bounds(obj), (0.0, 0.0, 0.0, 1.0), obj)

    def test_non_vertex_lines_are_ignored(self):
        """Нормали (vn) и текстурные координаты (vt) в габариты не входят"""
        obj = "v 0 0 0\nv 2 2 2\nvn 100 100 100\nvt 50 50\nf 1 2 1"
        cx, cy, cz, scale = compute_obj_bounds(obj)
        self.assertEqual((cx, cy, cz), (1.0, 1.0, 1.0))
        self.assertAlmostEqual(scale, TARGET_EXTENT / 2)

    def test_flat_model_does_not_divide_by_zero(self):
        """Все вершины в одной точке: размер нулевой, масштаб оставляем единичным"""
        self.assertEqual(compute_obj_bounds("v 5 5 5\nv 5 5 5"), (5.0, 5.0, 5.0, 1.0))


if __name__ == "__main__":
    unittest.main()


class GhostFramingTests(unittest.TestCase):
    """Своя модель из импорта: кадр по призраку оригинала, не по всему OBJ"""

    def test_frame_follows_the_ghost(self):
        # Своя модель ещё без подгонки: крошечная и далеко в стороне
        own = _cube(0.05, (500.0, 0.0, 0.0))
        ghost = _cube(10.0, (1.0, 2.0, 3.0))
        faces = lambda first: "\n".join(f"f {first + i} {first + i + 1} {first + i + 2}" for i in range(0, 6))
        obj = (own + "\nusemtl Material\n" + faces(1)
               + "\n" + ghost + "\nusemtl ghost:c_scattergun\n" + faces(9))
        cx, cy, cz, scale = compute_obj_bounds(obj)
        self.assertAlmostEqual(cx, 1.0, places=5)
        self.assertAlmostEqual(cy, 2.0, places=5)
        self.assertAlmostEqual(scale, TARGET_EXTENT / 10.0, places=5)

    def test_without_ghost_everything_counts(self):
        obj = _cube(2.0) + "\nusemtl Material\nf 1 2 3\n" + _cube(2.0, (10.0, 0.0, 0.0))
        cx, _, _, _ = compute_obj_bounds(obj)
        self.assertAlmostEqual(cx, 5.0, places=5)
