"""«Не красить»: детали War Paint, которые сохраняют прежнюю текстуру"""

import os
import tempfile
import unittest
from types import SimpleNamespace

import numpy as np
from PIL import Image

from src.services import paintkit_keep as pk


class PaintkitKeepTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.painted = os.path.join(self.tmp.name, 'warpaint.png')
        self.under = os.path.join(self.tmp.name, 'mine.png')
        Image.new('RGB', (64, 64), (200, 0, 0)).save(self.painted)       # War Paint
        Image.new('RGB', (128, 128), (0, 0, 200)).save(self.under)       # что было
        # Левая половина развёртки - деталь «Не красить»
        self.left = [((0.0, 0.0), (0.5, 0.0), (0.5, 1.0)), ((0.0, 0.0), (0.5, 1.0), (0.0, 1.0))]

    def tearDown(self):
        self.tmp.cleanup()

    def test_split_takes_keep_out_of_the_recipe(self):
        rest, kept = pk.split({'p1': 2, 'p2': pk.KEEP, 'g3': pk.KEEP})
        self.assertEqual(rest, {'p1': 2})
        self.assertEqual(kept, {'p2', 'g3'})
        self.assertEqual(pk.split(None), (None, set()))
        self.assertEqual(pk.split({'p2': pk.KEEP})[0], None)

    def test_polygons_of_kept_units_only(self):
        units = [SimpleNamespace(key='p1', uv=['a']), SimpleNamespace(key='p2', uv=['b', 'c'])]
        self.assertEqual(pk.polygons(units, {'p2'}), ['b', 'c'])

    def test_kept_part_gets_the_old_texture_back(self):
        out = pk.apply(self.painted, self.under, self.left, self.tmp.name)
        self.assertNotEqual(out, self.painted)
        img = np.asarray(Image.open(out).convert('RGB'))
        self.assertEqual(tuple(img[32, 8]), (0, 0, 200))       # деталь - как было
        self.assertEqual(tuple(img[32, 56]), (200, 0, 0))      # остальное - War Paint
        self.assertEqual(img.shape[:2], (64, 64))              # размер War Paint

    def test_nothing_to_keep_returns_the_war_paint(self):
        self.assertEqual(pk.apply(self.painted, self.under, [], self.tmp.name), self.painted)
        self.assertEqual(pk.apply(self.painted, '', self.left, self.tmp.name), self.painted)

    def test_mask_has_a_bleed_margin(self):
        m = pk.mask(self.left, (1024, 1024))
        self.assertEqual(m[512, 511], 255)
        self.assertEqual(m[512, 513], 255)       # запас за краем детали
        self.assertEqual(m[512, 600], 0)


if __name__ == '__main__':
    unittest.main()
