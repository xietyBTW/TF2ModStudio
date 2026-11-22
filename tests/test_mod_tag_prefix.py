"""Метка мода в папке обхода: два мода на одну шапку не делят файлы"""

import unittest

from src.services.model_build_service import ModelBuildService
from src.services.qc_skin_parser import resolve_cdmaterials
from src.shared.constants import bypass_prefix, mod_tag, strip_bypass_console


class ModTagPrefixTests(unittest.TestCase):
    def test_tag_is_short_stable_and_differs_between_mods(self):
        self.assertEqual(len(mod_tag("medic_hat.vpk")), 4)
        self.assertEqual(mod_tag("Medic_Hat.vpk"), mod_tag("medic_hat"))
        self.assertNotEqual(mod_tag("medic_hat.vpk"), mod_tag("spy_hat.vpk"))
        self.assertEqual(bypass_prefix("console"), "console")
        self.assertEqual(bypass_prefix("console", "medic_hat.vpk"),
                         "console\\" + mod_tag("medic_hat.vpk"))
        self.assertTrue(bypass_prefix("vgui", "a.vpk").startswith("vgui\\replay\\thumbnails\\"))

    def test_cdmaterials_of_another_mod_are_re_rooted_not_nested(self):
        old = "console\\" + mod_tag("old.vpk") + "\\models\\player\\items\\medic\\"
        new = bypass_prefix("console", "new.vpk")
        self.assertEqual(ModelBuildService.apply_cdmaterials_prefix(old, new),
                         new + "\\models\\player\\items\\medic\\")

    def test_game_lookup_drops_console_and_tag(self):
        tagged = "console/" + mod_tag("x.vpk") + "/models/player/items/medic"
        self.assertEqual(resolve_cdmaterials([tagged]), ["models/player/items/medic"])
        self.assertEqual(strip_bypass_console("console\\..\\..\\effects"), "..\\..\\effects")
        self.assertEqual(strip_bypass_console("models/console/x"), "models/console/x")


if __name__ == "__main__":
    unittest.main()
