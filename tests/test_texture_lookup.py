"""
Один поиск текстуры материала на превью и сборку (MaterialResolver.find_vtf)

Порядок как у игры: VMT -> $basetexture. Файл с именем материала и догадки -
только когда VMT нет. Случаи взяты из настоящих архивов TF2
"""

import unittest

from src.services import texture_guess
from src.services.material_resolver import MaterialResolver
from src.services.texture_build import game_source
from tests.fake_vpk import fake_reader, vmt

CD = ["models/weapons/c_items"]


def find(files, name, cdmaterials=CD, guesses=()):
    return MaterialResolver(fake_reader(files), "", apply_tint=False).find_vtf(
        name, cdmaterials, guesses)


class FindVtfTests(unittest.TestCase):
    def test_vmt_beats_the_file_with_the_name(self):
        # Valve: c_skullbat_hats смотрит на синюю текстуру, синий - на красную
        files = {
            "materials/models/weapons/c_items/c_skullbat_hats.vmt":
                vmt(basetexture="models/weapons/c_items/c_skullbat_hats_blue"),
            "materials/models/weapons/c_items/c_skullbat_hats.vtf": b"RED FILE",
            "materials/models/weapons/c_items/c_skullbat_hats_blue.vtf": b"BLUE FILE",
        }
        found = find(files, "c_skullbat_hats")
        self.assertEqual((found.data, found.path),
                         (b"BLUE FILE", "models/weapons/c_items/c_skullbat_hats_blue"))

    def test_source_extension_in_vmt_is_dropped_like_the_engine(self):
        files = {
            "materials/models/weapons/c_items/c_ubersaw_xms.vmt":
                vmt(basetexture="models/weapons/c_items/c_ubersaw_xms.psd"),
            "materials/models/weapons/c_items/c_ubersaw_xms.vtf": b"X",
        }
        self.assertEqual(find(files, "c_ubersaw_xms").path, "models/weapons/c_items/c_ubersaw_xms")

    def test_shader_without_basetexture_has_no_texture(self):
        # Линза Refract: файл с её именем - карта нормалей, не цвет
        files = {
            "materials/models/weapons/c_items/c_bazaar_sniper_lens.vmt":
                vmt(shader="Refract", normalmap="models/weapons/c_items/c_bazaar_sniper_lens"),
            "materials/models/weapons/c_items/c_bazaar_sniper_lens.vtf": b"NORMAL",
        }
        self.assertIsNone(find(files, "c_bazaar_sniper_lens"))

    def test_without_vmt_name_then_guesses(self):
        files = {"materials/models/player/scout/scout_head.vtf": b"HEAD"}
        found = find(files, "scout_head_red", ["models/player/scout"],
                     texture_guess.player_paths("scout", "scout_head_red"))
        self.assertEqual(found.path, "models/player/scout/scout_head")

    def test_build_takes_the_same_texture_as_the_preview(self):
        files = {
            "materials/models/weapons/c_items/gold_wrench.vmt":
                vmt(basetexture="models/weapons/c_models/c_wrench/c_wrench"),
            "materials/models/weapons/c_items/gold_wrench.vtf": b"UNUSED",
            "materials/models/weapons/c_models/c_wrench/c_wrench.vtf": b"WRENCH",
        }
        reader = fake_reader(files)
        from unittest.mock import patch
        with patch("src.services.game_vpk_reader.GameVpkReader", return_value=reader):
            built = game_source.find_original_vtf("gold_wrench", CD, "t.vpk", "m.vpk")
        self.assertEqual(built, find(files, "gold_wrench"))
        self.assertEqual(built.data, b"WRENCH")


class GuessTests(unittest.TestCase):
    def test_player_suffixes(self):
        self.assertEqual(texture_guess.player_paths("hvyweapon", "hvyweapon_hands_sheen"),
                         ["models/player/hvyweapon/hvyweapon_hands_sheen",
                          "models/player/hvyweapon/hvyweapon_hands"])
        self.assertEqual(texture_guess.player_paths(None, "x"), [])

    def test_weapon_dirs_in_one_place(self):
        self.assertEqual(texture_guess.weapon_paths("C_Gun")[2], "models/weapons/c_items/c_gun")


if __name__ == "__main__":
    unittest.main()
