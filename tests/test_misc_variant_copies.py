"""Материалы «Прочего» (убер и зомби тела класса) и служебные рядом с ними"""

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from src.domain.preview.vmt_edits import VmtEdits
from src.services.texture_build import game_source
from src.services.vpk_texture_builder import VpkTextureBuilder

VMT = '"VertexLitGeneric"\n{{\n\t"$basetexture" "models/{}"\n}}\n'


def _Slots(folder):
    from src.services.build_context import MaterialSlots
    return MaterialSlots(
        vtf_output_path=Path(folder), vmt_path=Path(folder) / "scout_red.vmt",
        patched_cdmaterials_path="console/models/player/scout",
        original_cdmaterials_paths=["models/player/scout"])


class SharedTextureTests(unittest.TestCase):
    def test_heavy_hands_follow_the_body(self):
        # Руки хэви (hvyweapon_red_sheen) в игре смотрят на текстуру тела:
        # со своей текстурой тела они оставались стоковыми. Материал части
        # (редактируемое имя) со своей логикой игровой строки не трогается
        with tempfile.TemporaryDirectory() as d, tempfile.TemporaryDirectory() as game:
            slots = _Slots(d)
            body_game = Path(game) / "hvyweapon_red.vmt"
            body_game.write_text(VMT.format("player/hvyweapon/hvyweapon_red"))
            slots.vtf("hvyweapon_red").write_bytes(b"custom body")
            slots.vmt("hvyweapon_red").write_text(VMT.format("x"))
            for name in ("hvyweapon_red_sheen", "hvyweapon_red_part1_blue"):
                slots.vmt(name).write_text(VMT.format("player/hvyweapon/hvyweapon_red"))
            with patch.object(game_source, "find_original_vmt",
                              side_effect=lambda name, ctx, s: str(body_game)
                              if name == "hvyweapon_red" else None):
                VpkTextureBuilder._follow_shared_textures(None, slots)
            self.assertIn("console/models/player/scout/hvyweapon_red",
                          slots.vmt("hvyweapon_red_sheen").read_text())
            self.assertIn("models/player/hvyweapon/hvyweapon_red",
                          slots.vmt("hvyweapon_red_part1_blue").read_text())
            self.assertNotIn("console", slots.vmt("hvyweapon_red_part1_blue").read_text())

    def test_game_copy_is_not_followed(self):
        # Тело осталось игровым (копия игровой VTF) - рукам следовать не за чем
        with tempfile.TemporaryDirectory() as d, tempfile.TemporaryDirectory() as game:
            slots = _Slots(d)
            body_game = Path(game) / "hvyweapon_red.vmt"
            body_game.write_text(VMT.format("player/hvyweapon/hvyweapon_red"))
            slots.vtf("hvyweapon_red").write_bytes(b"game body")
            slots.game_copies.add("hvyweapon_red")
            slots.vmt("hvyweapon_red_sheen").write_text(VMT.format("player/hvyweapon/hvyweapon_red"))
            with patch.object(game_source, "find_original_vmt", return_value=str(body_game)):
                VpkTextureBuilder._follow_shared_textures(None, slots)
            self.assertNotIn("console", slots.vmt("hvyweapon_red_sheen").read_text())


class EditedVmtTests(unittest.TestCase):
    """Правка VMT из редактора у доп. материалов: голова и «Прочее» не уходят
    в мод игровыми"""

    def test_edits_reach_extra_materials(self):
        from src.services.edited_vmt_service import EditedVMTService
        from src.shared.constants import EXTRA_TEX_USE_GAME_ORIGINAL

        with tempfile.TemporaryDirectory() as d, tempfile.TemporaryDirectory() as game, \
                tempfile.TemporaryDirectory() as edits:
            slots = _Slots(d)
            slots.vmt_path.write_text(VMT.format("scout_red"))
            own = Path(d) / "own.vtf"
            own.write_bytes(b"VTF own")
            originals = {}
            for name in ("scout_head_red_invun", "scout_head_zombie"):
                originals[name] = Path(game) / f"{name}.vmt"
                originals[name].write_text(VMT.format(name))
            answers = {"scout_head_red_invun": str(own),
                       "scout_head_zombie": EXTRA_TEX_USE_GAME_ORIGINAL}
            with EditedVMTService.use(VmtEdits()), \
                    patch.object(game_source, "find_original_vmt",
                                 side_effect=lambda name, ctx, s: str(originals.get(name, "")) or None):
                for name in answers:
                    EditedVMTService.save_edited_vmt(
                        name, VMT.format(name).replace("}", '\t"$selfillum" "1"\n}'))
                VpkTextureBuilder._build_extra_material_textures(
                    list(answers), "scout", None, slots,
                    SimpleNamespace(for_material=lambda _: SimpleNamespace(custom_vtf_path=None)),
                    lambda name, *_: answers[name], None)
            invun = slots.vmt("scout_head_red_invun").read_text()
            zombie = slots.vmt("scout_head_zombie").read_text()
        # Своя текстура: $basetexture правки ведёт на неё
        self.assertIn("$selfillum", invun)
        self.assertIn("console/models/player/scout/scout_head_red_invun", invun)
        # Игровой: правка как есть, текстура игровая
        self.assertIn("$selfillum", zombie)
        self.assertIn("models/scout_head_zombie", zombie)

    def test_hat_without_game_paints_strips_the_edit(self):
        # Второй материал шапки: правка начинается с игрового VMT с краской.
        # Без «Красок из игры» главный её теряет, и второй должен тоже
        from src.services.edited_vmt_service import EditedVMTService

        painted = ('"VertexLitGeneric"\n{\n\t"$basetexture" "models/x"\n'
                   '\t"$colortint_base" "{ 255 255 255 }"\n\t"Proxies"\n\t{\n'
                   '\t\t"ItemTintColor"\n\t\t{\n\t\t\t"resultVar" "$colortint_tmp"\n\t\t}\n\t}\n}\n')
        with tempfile.TemporaryDirectory() as d, tempfile.TemporaryDirectory() as edits:
            slots = _Slots(d)
            target = slots.vmt("c_energydrink")
            target.write_text(VMT.format("x"))
            with EditedVMTService.use(VmtEdits()):
                EditedVMTService.save_edited_vmt("c_energydrink", painted)
                VpkTextureBuilder._apply_edited_vmt(
                    "c_energydrink", target, None, slots, True, strip_paints=True)
            text = target.read_text()
        self.assertNotIn("ItemTintColor", text)
        self.assertNotIn("$colortint_base", text)


if __name__ == "__main__":
    unittest.main()
