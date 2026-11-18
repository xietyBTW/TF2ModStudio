"""
Своя радужка глаз персонажа

Глаз - шейдер EyeRefract: $basetexture у него нет, картинка - радужка $iris.
Сборка пишет игровой VMT глаза, где $iris смотрит на текстуру мода, и только
когда на карточке глаза своя картинка
"""

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from src.services import vmt_parse
from src.services.texture_build import extra_materials, game_source

EYE = ('"EyeRefract"\r\n{\r\n'
       '\t"$Iris"               "models/player/shared/eye-iris-blue"  // RGB + cornea noise in A\r\n'
       '\t"$CorneaTexture"      "models/player/shared/eye-cornea"\r\n'
       '\t"$EyeballRadius" "0.7"\r\n'
       '\t"Eyes_dx8"\r\n\t{\r\n'
       '\t\t"$basetexture" "models/player/shared/dxlevel80/eyeball_l"\r\n'
       '\t\t"$iris"        "models/player/shared/dxlevel80/iris_blue_l"\r\n\t}\r\n}\r\n')


def _slots(folder):
    from src.services.build_context import MaterialSlots
    return MaterialSlots(
        vtf_output_path=Path(folder), vmt_path=Path(folder) / "scout_red.vmt",
        patched_cdmaterials_path="console/models/player/scout",
        original_cdmaterials_paths=["models/player/scout"])


class EyeVmtTests(unittest.TestCase):
    def test_own_image_goes_to_iris_not_basetexture(self):
        with tempfile.TemporaryDirectory() as d, tempfile.TemporaryDirectory() as game:
            slots = _slots(d)
            game_eye = Path(game) / "eyeball_l.vmt"
            game_eye.write_text(EYE, encoding="utf-8")
            img = Path(game) / "iris.png"
            img.write_bytes(b"png")

            def render(name, _img, slots_, _tex):
                slots_.vtf(name).write_bytes(b"VTF")

            with patch.object(game_source, "find_original_vmt", return_value=str(game_eye)), \
                    patch.object(extra_materials, "_render_own_image", side_effect=render):
                extra_materials.build_extra_material_textures(
                    ["eyeball_l"], "scout", None, slots, None,
                    lambda *_: str(img), None, tg_rows=[], deferred=[])
            doc = vmt_parse.parse(slots.vmt("eyeball_l").read_text(encoding="utf-8"))

        self.assertEqual(doc.shader.lower(), "eyerefract")
        self.assertEqual(doc.path("iris"), "console/models/player/scout/eyeball_l")
        self.assertIsNone(doc.get("basetexture"), "глазу $basetexture не нужен")
        self.assertEqual(doc.path("corneatexture"), "models/player/shared/eye-cornea")
        # Запасной блок DirectX 8 остался игровым
        self.assertEqual(doc.block("eyes_dx8").get("iris"),
                         "models/player/shared/dxlevel80/iris_blue_l")

    def test_ordinary_material_is_not_an_eye(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "scout_red_invun.vmt"
            path.write_text('"VertexLitGeneric"\n{\n\t"$basetexture" "x"\n}\n', encoding="utf-8")
            self.assertFalse(game_source.is_eye_vmt(path))
            self.assertFalse(game_source.is_eye_vmt(None))


class AskTests(unittest.TestCase):
    def test_untouched_eyes_are_not_asked(self):
        from src.app.build_editor import BuildEditor

        uploads = {"eyeball_r": "my_iris.png"}
        preview = SimpleNamespace(
            misc_materials=["scout_red_invun", "eyeball_l", "eyeball_r"],
            eye_materials=["eyeball_l", "eyeball_r"],
            textures=SimpleNamespace(uploaded_for_mat=uploads.get))
        editor = BuildEditor.__new__(BuildEditor)
        editor._host = SimpleNamespace(preview=preview)
        self.assertEqual(editor._misc_to_ask(), ["scout_red_invun", "eyeball_r"])


if __name__ == "__main__":
    unittest.main()
