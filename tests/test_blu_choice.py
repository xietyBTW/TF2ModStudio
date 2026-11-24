"""Выбор синей у командной карточки: показ, сохранение, ответ сборке"""

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from src.domain.preview.session import PreviewSession
from src.domain.preview.texture_state import PreviewTextureState
from src.shared.constants import Team


class BluChoiceTests(unittest.TestCase):
    def setUp(self):
        self._tmp = TemporaryDirectory()
        d = Path(self._tmp.name)
        self.red_png, self.game_red, self.game_blu, self.own_blu = (
            str(d / n) for n in ("red.png", "game_red.png", "game_blu.png", "own.png"))
        for p in (self.red_png, self.game_red, self.game_blu, self.own_blu):
            Path(p).write_bytes(b"x")
        t = PreviewTextureState()
        t.material_names = ["hat", "hat_1"]
        t.blu_name_map = {"hat": "hat_blue", "hat_1": "hat_1"}
        t.vpk_red_tex_map = {"hat": self.game_red}
        t.vpk_blu_tex_map = {"hat": self.game_blu}
        t.textures[Team.RED]["hat"] = self.red_png
        t.active_team = Team.BLU
        self.t = t

    def tearDown(self):
        self._tmp.cleanup()

    def test_only_team_cards_get_a_choice_and_game_is_default(self):
        self.assertEqual(self.t.blu_choices(), {"hat": "game"})
        self.assertEqual(self.t.resolve_base("hat"), self.game_blu)
        self.t.active_team = Team.RED
        self.assertEqual(self.t.blu_choices(), {})

    def test_like_red_shows_red_picture_on_blue(self):
        self.t.set_blu_choice("hat", "red")
        self.assertEqual(self.t.blu_choices(), {"hat": "red"})
        self.assertEqual(self.t.resolve_base("hat"), self.red_png)

    def test_own_upload_wins_and_choice_drops_it(self):
        self.t.set_blu_choice("hat", "red")
        self.t.set_texture("hat", self.own_blu)
        self.assertEqual(self.t.blu_choices(), {"hat": "own"})
        self.assertNotIn("hat", self.t.blu_like_red)
        self.t.set_blu_choice("hat", "game")
        self.assertEqual(self.t.blu_choices(), {"hat": "game"})
        self.assertNotIn("hat", self.t.textures[Team.BLU])

    def test_upload_is_seen_only_on_its_team(self):
        """Меню «Вернуть игровую» - только там, где своя картинка лежит"""
        self.assertFalse(self.t.has_upload("hat"))       # показана синяя
        self.t.active_team = Team.RED
        self.assertTrue(self.t.has_upload("hat"))
        self.assertFalse(self.t.has_upload("hat_1"))

    def test_build_material_maps_back_to_red_card(self):
        self.assertEqual(self.t.red_of_blu("hat_blue"), "hat")
        self.assertIsNone(self.t.red_of_blu("hat_1"))
        self.assertIsNone(self.t.red_of_blu("other_blue"))

    def test_choice_survives_work_round_trip(self):
        s = PreviewSession()
        s.textures.textures[Team.RED]["hat"] = self.red_png
        s.textures.blu_name_map = {"hat": "hat_blue"}
        s.textures.set_blu_choice("hat", "red")
        edits = s.user_edits()
        fresh = PreviewSession()
        fresh.apply_user_edits(edits)
        self.assertEqual(fresh.textures.blu_like_red, {"hat"})
        fresh.forget_user_edits()
        self.assertEqual(fresh.textures.blu_like_red, set())

    def test_other_item_forgets_choice(self):
        s = PreviewSession()
        s.begin_item("hat_a", "hat")
        s.textures.blu_name_map = {"hat": "hat_blue"}
        s.textures.set_blu_choice("hat", "red")
        s.begin_item("hat_a", "hat")
        self.assertEqual(s.textures.blu_like_red, {"hat"})
        s.begin_item("hat_b", "hat")
        self.assertEqual(s.textures.blu_like_red, set())


if __name__ == "__main__":
    unittest.main()
