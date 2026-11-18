"""
Нетронутые текстуры в моде - ссылкой на игру (texture_build.game_links)
"""

import hashlib
import tempfile
import unittest
from pathlib import Path

from src.services.texture_build.game_links import link_to_game

GAME = b"VTF\x00game"
OWN = b"VTF\x00own"
CD = "console/models/weapons/c_gun"


def vmt(texture: str) -> bytes:
    return f'"VertexLitGeneric"\r\n{{\r\n\t"$basetexture" "{texture}"\r\n}}\r\n'.encode()


class GameLinksTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name) / "materials"
        self.mod = self.root / CD
        self.mod.mkdir(parents=True)
        self.known = {hashlib.sha1(GAME).hexdigest(): "models/weapons/c_gun/c_gun_scope"}

    def tearDown(self):
        self._tmp.cleanup()

    def put(self, name, data, texture=None, folder=None):
        folder = folder or self.mod
        folder.mkdir(parents=True, exist_ok=True)
        if data is not None:
            (folder / f"{name}.vtf").write_bytes(data)
        (folder / f"{name}.vmt").write_bytes(vmt(texture or f"{CD}/{name}"))

    def test_game_copies_leave_and_vmts_point_at_the_game(self):
        self.put("c_gun", OWN)
        self.put("c_gun_scope", GAME)
        # Синяя пара «как красная»: копия копии, те же байты
        self.put("c_gun_scope_blue", GAME)
        # Зеркало по оригинальному пути смотрит на VTF в console-папке
        self.put("c_gun_scope", None, f"{CD}/c_gun_scope", self.root / "models/weapons/c_gun")
        self.assertEqual(link_to_game(self.root, self.known), 2)

        game = vmt("models/weapons/c_gun/c_gun_scope")
        self.assertEqual((self.mod / "c_gun_scope.vmt").read_bytes(), game)
        self.assertEqual((self.mod / "c_gun_scope_blue.vmt").read_bytes(), game)
        self.assertEqual((self.root / "models/weapons/c_gun/c_gun_scope.vmt").read_bytes(), game)
        self.assertFalse((self.mod / "c_gun_scope.vtf").exists())
        self.assertFalse((self.mod / "c_gun_scope_blue.vtf").exists())
        # Своя картинка человека остаётся как была
        self.assertEqual((self.mod / "c_gun.vtf").read_bytes(), OWN)
        self.assertEqual((self.mod / "c_gun.vmt").read_bytes(), vmt(f"{CD}/c_gun"))

    def test_reference_that_cannot_be_moved_keeps_the_copy(self):
        self.put("c_gun_scope", GAME)
        (self.mod / "odd.vmt").write_bytes(
            f'"VertexLitGeneric"\n{{\n\t$basetexture {CD}/c_gun_scope\n}}\n'.encode())
        self.assertEqual(link_to_game(self.root, self.known), 0)
        self.assertTrue((self.mod / "c_gun_scope.vtf").exists())

    def test_nothing_known_changes_nothing(self):
        self.put("c_gun_scope", GAME)
        self.assertEqual(link_to_game(self.root, {}), 0)
        self.assertTrue((self.mod / "c_gun_scope.vtf").exists())


if __name__ == "__main__":
    unittest.main()
