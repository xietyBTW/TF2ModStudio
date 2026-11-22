"""Мазки по частям на шапке с маской краски: банка красит только маску"""

import os
import tempfile
import unittest

from PIL import Image

from src.services import texture_compose_service as tcs
from src.services import vmt_tint


class PartStrokesKeepPaintMaskTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        # Левая половина - маска краски (альфа 255), правая - не красится
        stock = os.path.join(self.tmp.name, "hat.png")
        img = Image.new("RGBA", (64, 64), (50, 50, 50, 0))
        img.paste((50, 50, 50, 255), (0, 0, 32, 64))
        img.save(stock)
        vmt_tint.apply_to_png(stock, vmt_tint.TintSpec((200, 0, 0)))
        self.stock = stock

    def tearDown(self):
        self.tmp.cleanup()

    def _stroke(self):
        # Полоса u 0..0.25 на всю высоту
        tris = (((0, 0), (0.25, 0), (0.25, 1)), ((0, 0), (0.25, 1), (0, 1)))
        layer = tcs.Layer(polygons=tris, color="#00ff00", exact=True)
        out = os.path.join(self.tmp.name, "parts_1.png")
        self.assertEqual(tcs.compose(self.stock, [layer], out, frames=1), out)
        return out

    def test_composite_keeps_game_mask_outside_strokes(self):
        out = self._stroke()
        raw = Image.open(vmt_tint.game_texture(out)).convert("RGBA")
        self.assertNotEqual(vmt_tint.game_texture(out), out)
        self.assertEqual(raw.getpixel((5, 30))[3], 0)            # мазок: банка не красит
        self.assertEqual(raw.getpixel((28, 30)), (50, 50, 50, 255))   # маска игры цела
        self.assertEqual(raw.getpixel((50, 30))[3], 0)           # вне маски как было

    def test_other_paint_recolours_only_the_mask(self):
        out = self._stroke()
        shown = Image.open(out).convert("RGBA")
        spec = vmt_tint.paintable(out)
        self.assertIsNotNone(spec)
        blue = vmt_tint.painted(vmt_tint.game_texture(out),
                                vmt_tint.TintSpec((0, 0, 255)), self.tmp.name)
        painted = Image.open(blue).convert("RGBA")
        self.assertEqual(painted.getpixel((5, 30)), shown.getpixel((5, 30)))
        self.assertEqual(painted.getpixel((50, 30))[:3], (50, 50, 50))
        r, g, b, _ = painted.getpixel((28, 30))
        self.assertTrue(b > 0 and r == 0 and g == 0)

    def test_own_texture_without_sidecars_is_untouched(self):
        own = os.path.join(self.tmp.name, "own.png")
        Image.new("RGBA", (8, 8), (1, 2, 3, 255)).save(own)
        self.assertEqual(vmt_tint.game_texture(own), own)


if __name__ == "__main__":
    unittest.main()
