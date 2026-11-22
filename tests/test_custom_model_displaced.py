"""«Убрать свою модель» возвращает карточкам то, что заняли картинки из её файла"""

import os
import tempfile
import threading
import unittest
from types import SimpleNamespace

from PIL import Image

from src.app.custom_model_editor import CustomModelEditor
from src.domain.preview.session import PreviewSession
from src.shared.constants import Team


class DisplacedTexturesTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.png = {}
        for name, rgb in (("mine", (200, 0, 0)), ("from_file", (0, 200, 0)), ("later", (0, 0, 200))):
            self.png[name] = os.path.join(self.tmp.name, f"{name}.png")
            Image.new("RGB", (4, 4), rgb).save(self.png[name])
        ps = PreviewSession()
        ps.textures.material_names = ["hat", "lens"]
        self.ps = ps
        self.ed = CustomModelEditor(SimpleNamespace(preview=ps, _lock=threading.RLock()))
        self.ed._imported_mesh = ("src.obj", SimpleNamespace(textures={"Material": self.png["from_file"]}))

    def tearDown(self):
        self.tmp.cleanup()

    def _slot(self, team=Team.RED):
        return self.ps.textures.textures.get(team, {}).get("hat")

    def test_own_texture_comes_back(self):
        self.ps.textures.set_texture("hat", self.png["mine"])
        self.assertEqual(self.ed._place_imported_textures("src.obj", ["hat"]), 1)
        self.assertEqual(self._slot(), self.png["from_file"])
        with self.ed._host._lock:
            self.ed._restore_displaced()
        self.assertEqual(self._slot(), self.png["mine"])
        self.assertEqual(self._slot(Team.BLU), self.png["mine"])
        self.assertEqual(self.ps.custom_displaced, {})

    def test_empty_card_goes_back_to_game(self):
        self.ed._place_imported_textures("src.obj", ["hat"])
        self.ed._restore_displaced()
        self.assertIsNone(self._slot())

    def test_card_changed_by_hand_is_kept(self):
        self.ps.textures.set_texture("hat", self.png["mine"])
        self.ed._place_imported_textures("src.obj", ["hat"])
        self.ps.textures.set_texture("hat", self.png["later"])
        self.ed._restore_displaced()
        self.assertEqual(self._slot(), self.png["later"])

    def test_record_survives_the_saved_work(self):
        self.ps.textures.set_texture("hat", self.png["mine"])
        self.ed._place_imported_textures("src.obj", ["hat"])
        edits = self.ps.user_edits()
        back = PreviewSession()
        back.apply_user_edits(edits)
        self.assertEqual(back.custom_displaced["hat"]["red"], self.png["mine"])


if __name__ == "__main__":
    unittest.main()
