"""«Только форма»: вся своя геометрия в одном главном материале, карточка одна"""

import os
import tempfile
import unittest

from src.domain.preview.session import PreviewSession
from src.services.smd_service import SMDService, shape_only_material

_HEAD = "version 1\nnodes\n0 \"bone\" -1\nend\nskeleton\ntime 0\n0 0 0 0 0 0 0\nend\ntriangles\n"
_TRI = "0 0 0 0 0 0 1 0 0\n0 1 0 0 0 0 1 1 0\n0 0 1 0 0 0 1 0 1\n"


def _smd(path, materials):
    with open(path, "w", encoding="utf-8") as f:
        f.write(_HEAD + "".join(f"{m}\n{_TRI}" for m in materials) + "end\n")


class ShapeOnlyOneMaterialTests(unittest.TestCase):
    def test_target_is_texturegroup_main_else_most_common(self):
        names = ["lens", "lens", "lens", "hat"]
        self.assertEqual(shape_only_material(names, "HAT"), "hat")
        self.assertEqual(shape_only_material(names, None), "lens")
        self.assertEqual(shape_only_material(names, "missing"), "lens")
        self.assertEqual(shape_only_material([], "hat"), "")

    def test_build_puts_every_triangle_into_the_main_material(self):
        with tempfile.TemporaryDirectory() as tmp:
            game, user, out = (os.path.join(tmp, n) for n in ("game.smd", "user.smd", "out.smd"))
            _smd(game, ["hat", "hat", "lens", "lens", "lens"])
            _smd(user, ["Material"] * 6)
            qc = os.path.join(tmp, "hat.qc")
            with open(qc, "w", encoding="utf-8") as f:
                f.write('$texturegroup "skinfamilies"\n{\n{ "hat" "lens" }\n}\n')
            SMDService.replace_model_sections(user, game, out, qc_path=qc)
            with open(out, encoding="utf-8") as f:
                body = f.read().split("triangles\n", 1)[1]
            mats = [ln for ln in body.splitlines() if ln and not ln[0].isdigit() and ln != "end"]
            self.assertEqual(mats, ["hat"] * 6)

    def test_cards_show_only_the_main_material(self):
        ps = PreviewSession()
        ps.textures.material_names = ["hat", "lens"]
        ps.textures.main_material = "hat"
        self.assertEqual(ps.card_materials(), ["hat", "lens"])
        ps.custom_smd_path = "user.smd"
        self.assertEqual(ps.card_materials(), ["hat"])
        ps.custom_keep_materials = True
        self.assertEqual(ps.card_materials(), ["hat", "lens"])

    def test_own_meshes_wear_the_main_card_in_3d(self):
        with tempfile.TemporaryDirectory() as tmp:
            mine = os.path.join(tmp, "mine.png")
            open(mine, "wb").close()
            ps = PreviewSession()
            ps.textures.material_names = ["hat", "lens"]
            ps.textures.main_material = "hat"
            ps.textures.set_texture("hat", mine)
            ps.custom_smd_path = "user.smd"
            ps.custom_mesh_materials = ["Material", "Material.001"]
            scene = ps.scene_textures()
            self.assertEqual(scene["Material"], mine)
            self.assertEqual(scene["Material.001"], mine)
            self.assertEqual(ps.scene_names("hat")[-2:], ["Material", "Material.001"])
            ps.custom_keep_materials = True
            self.assertNotIn("Material", ps.scene_textures())


if __name__ == "__main__":
    unittest.main()
