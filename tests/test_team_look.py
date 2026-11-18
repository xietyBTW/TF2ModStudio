"""
Синий VMT мода возвращает командный вид игры (texture_build.team_look)

Синий пишется копией красного VMT мода, а у Valve команды отличаются краской
в самом VMT: у Battle Balaclava RED { 90 81 67 }, BLU { 67 72 80 }. Без этого
прохода маска синего хэви в игре была цвета красных
"""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from src.services import vmt_parse
from src.services.texture_build.team_look import inherit, inherit_pairs
from tests.fake_vpk import fake_reader

CD = "models/workshop/player/items/heavy/balaclava"


def game_vmt(tint: str, extra: str = "") -> str:
    return ('"VertexLitGeneric"\n{\n'
            f'\t"$basetexture" "{CD}/balaclava_color"\n'
            '\t"$phongboost" "0.2"\n'
            '\t"$blendtintbybasealpha" "1"\n'
            f'\t"$colortint_base" "{tint}"\n'
            f'\t"$color2" "{tint}"\n{extra}'
            '\t"Proxies"\n\t{\n\t\t"ItemTintColor"\n\t\t{\n'
            '\t\t\t"resultVar" "$colortint_tmp"\n\t\t}\n\t}\n}\n')


RED = game_vmt("{ 90 81 67 }")
BLU = game_vmt("{ 67 72 80 }")


def mod_copy_of_red(**changes) -> str:
    """Как пишет сборка: копия красного с текстурой мода и правками"""
    text = RED.replace(f"{CD}/balaclava_color", f"console/{CD}/balaclava_blue")
    for old, new in changes.items():
        text = text.replace(old, new)
    return text


def run(text: str, red=RED, blu=BLU):
    with tempfile.TemporaryDirectory() as d:
        path = Path(d) / "balaclava_blue.vmt"
        path.write_text(text, encoding="utf-8")
        changed = inherit(path, red, blu)
        return changed, vmt_parse.parse(path.read_text(encoding="utf-8"))


class InheritTests(unittest.TestCase):
    def test_blue_gets_the_team_paint_and_keeps_the_mod_texture(self):
        changed, doc = run(mod_copy_of_red())
        self.assertTrue(changed)
        self.assertEqual(doc.color("colortint_base"), (67, 72, 80))
        self.assertEqual(doc.color("color2"), (67, 72, 80))
        self.assertEqual(doc.path("basetexture"), f"console/{CD}/balaclava_blue")

    def test_edits_of_the_mod_win(self):
        # Человек поднял блеск - это его правка, а не командная разница
        _changed, doc = run(mod_copy_of_red(**{'"$phongboost" "0.2"': '"$phongboost" "3"'}))
        self.assertEqual(doc.number("phongboost"), 3.0)
        self.assertEqual(doc.color("colortint_base"), (67, 72, 80))

    def test_paint_removed_by_the_mod_stays_removed(self):
        # «Краски из игры» сняты: краски нет и у синего
        stripped = mod_copy_of_red(**{'\t"$colortint_base" "{ 90 81 67 }"\n': "",
                                      '\t"$color2" "{ 90 81 67 }"\n': ""})
        _changed, doc = run(stripped)
        self.assertIsNone(doc.get("colortint_base"))
        self.assertIsNone(doc.get("color2"))

    def test_other_team_differences_come_too(self):
        # Свечение и цвет невидимости тоже бывают командными
        red = game_vmt("{ 90 81 67 }", '\t"$cloakcolortint" "[1 .5 .4]"\n')
        blu = game_vmt("{ 67 72 80 }", '\t"$cloakcolortint" "[.4 .5 1]"\n')
        mine = red.replace(f"{CD}/balaclava_color", f"console/{CD}/balaclava_blue")
        _changed, doc = run(mine, red, blu)
        self.assertEqual(doc.get("cloakcolortint"), "[.4 .5 1]")

    def test_same_look_in_game_changes_nothing(self):
        changed, _doc = run(mod_copy_of_red(), RED, RED)
        self.assertFalse(changed)


class PairsTests(unittest.TestCase):
    def test_pairs_find_game_vmts_and_skip_shared_and_missing(self):
        reader = fake_reader({f"materials/{CD}/balaclava.vmt": RED.encode(),
                              f"materials/{CD}/balaclava_blue.vmt": BLU.encode()})
        with tempfile.TemporaryDirectory() as d, \
                patch("src.services.game_vpk_reader.GameVpkReader", return_value=reader):
            (Path(d) / "balaclava_blue.vmt").write_text(mod_copy_of_red(), encoding="utf-8")
            done = inherit_pairs(d, [("balaclava", "balaclava_blue"), ("lens", "lens"),
                                     ("balaclava_1", "balaclava_1_blue")], [CD], ["t", "m"])
            doc = vmt_parse.parse((Path(d) / "balaclava_blue.vmt").read_text(encoding="utf-8"))
        self.assertEqual(done, ["balaclava_blue"])
        self.assertEqual(doc.color("colortint_base"), (67, 72, 80))


if __name__ == "__main__":
    unittest.main()
