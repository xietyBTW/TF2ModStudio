"""
Австралий - своя карточка, а не переключатель показа поверх главной

У варианта своя карточка с той же геометрией, и всё, что умеет карточка, -
текстура, части, настройки - у него своё. Иначе положить свою текстуру
австралия было бы некуда, а части красили бы главную
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from PIL import Image

from src.domain.preview.session import PreviewSession
from src.domain.preview.texture_state import SINGLE_TEX_KEY


class VariantCardTests(unittest.TestCase):
    def setUp(self):
        self._dir = tempfile.TemporaryDirectory()
        root = Path(self._dir.name)
        self.gold = str(root / 'gold.png')
        self.base = str(root / 'base.png')
        self.mine = str(root / 'mine.png')
        for p in (self.gold, self.base, self.mine):
            Image.new('RGBA', (4, 4), (255, 255, 255, 255)).save(p)
        s = PreviewSession()
        s.weapon_key = 'c_scattergun'
        t = s.textures
        t.material_names = [SINGLE_TEX_KEY]
        t.vpk_red_tex_map = {SINGLE_TEX_KEY: self.base}
        t.australium_frame = self.gold
        t.australium_mat_name = 'c_scattergun_gold'
        self.s, self.t = s, t

    def tearDown(self):
        self._dir.cleanup()

    def test_the_variant_card_stands_in_for_the_main_one_while_toggled(self):
        """Как RED/BLU: карточка одна, что на ней - решает переключатель"""
        self.assertEqual(self.s.card_materials(), [SINGLE_TEX_KEY])
        self.assertEqual(self.s.visible_textures(), {SINGLE_TEX_KEY: self.base})
        self.t.australium_active = True
        self.assertEqual(self.s.card_materials(), ['c_scattergun_gold'])
        self.assertEqual(self.s.visible_textures(), {'c_scattergun_gold': self.gold})

    def test_own_texture_on_the_variant_shows_on_the_model_when_toggled(self):
        self.t.set_texture('c_scattergun_gold', self.mine)
        # Главная не тронута ни в альбоме, ни на модели, пока вариант выключен
        self.assertEqual(self.s.visible_textures()[SINGLE_TEX_KEY], self.base)
        self.assertEqual(self.s.scene_textures()[SINGLE_TEX_KEY], self.base)
        self.t.australium_active = True
        self.assertEqual(self.s.visible_textures()['c_scattergun_gold'], self.mine)
        self.assertEqual(self.t.variant_display_texture(), self.mine)
        self.assertEqual(self.s.scene_textures()[SINGLE_TEX_KEY], self.mine)

    def test_vpk_mod_shows_its_variant_in_place_of_the_main(self):
        """Австралий модели мода (mod_variant) - так же на месте главной"""
        self.t.australium_active = True
        self.s.custom_vpk_mode = True
        self.assertEqual(self.s.card_materials(), ['c_scattergun_gold'])

    def test_variant_texture_goes_to_the_build_as_its_own_material(self):
        self.t.set_texture('c_scattergun_gold', self.mine)
        from src.domain.preview import variant_card
        self.assertEqual(variant_card.build_images(self.t), {'c_scattergun_gold': self.mine})
        self.assertEqual(self.t.uploaded_slot_paths(), {})
        self.assertEqual(self.t.uploaded_for_mat('c_scattergun_gold'), self.mine)


if __name__ == '__main__':
    unittest.main()


class VariantSourceTests(unittest.TestCase):
    """Откуда картинка у австралия: игровое, как обычная, как красное, своё"""

    def setUp(self):
        from src.shared.constants import Team
        self.Team = Team
        self._dir = tempfile.TemporaryDirectory()
        root = Path(self._dir.name)
        self.p = {}
        for n in ('gold', 'gold_blu', 'base', 'base_blu', 'mine', 'mine_blu'):
            self.p[n] = str(root / f'{n}.png')
            Image.new('RGBA', (4, 4), (255, 255, 255, 255)).save(self.p[n])
        s = PreviewSession()
        t = s.textures
        t.material_names = ['c_ambassador']
        t.blu_name_map = {'c_ambassador': 'c_ambassador_blue'}
        t.vpk_red_tex_map = {'c_ambassador': self.p['base']}
        t.vpk_blu_tex_map = {'c_ambassador': self.p['base_blu']}
        t.australium_frame = self.p['gold']
        t.australium_mat_name = 'c_ambassador_gold'
        t.australium_active = True
        self.s, self.t = s, t

    def tearDown(self):
        self._dir.cleanup()

    def test_game_by_default_and_base_on_own_geometry(self):
        from src.domain.preview import variant_card
        self.assertEqual(variant_card.choice(self.t), 'game')
        self.assertEqual(self.t.resolve_card('c_ambassador_gold'), self.p['gold'])
        self.s.custom_smd_path = 'mine.smd'
        self.assertEqual(variant_card.choice(self.t), 'base')
        self.t.set_texture('c_ambassador', self.p['mine'])
        self.assertEqual(self.t.resolve_card('c_ambassador_gold'), self.p['mine'])
        self.assertEqual(variant_card.build_images(self.t), {'c_ambassador_gold': self.p['mine']})

    def test_choice_drops_own_picture(self):
        from src.domain.preview import variant_card
        self.t.set_texture('c_ambassador_gold', self.p['mine'])
        self.assertEqual(variant_card.choice(self.t), 'own')
        self.assertTrue(variant_card.set_choice(self.t, 'game'))
        self.assertEqual(variant_card.choice(self.t), 'game')
        self.assertFalse(variant_card.set_choice(self.t, 'red'))      # синего золота нет

    def test_team_gold_like_the_ambassador(self):
        from src.domain.preview import variant_card
        Team = self.Team
        self.t.australium_blu_frame = self.p['gold_blu']
        self.t.australium_blu_mat = 'c_ambassador_blue_gold'
        self.assertTrue(self.t.is_team_material('c_ambassador_gold'))
        self.t.set_texture('c_ambassador_gold', self.p['mine'])        # своя - только красным
        self.t.active_team = Team.BLU
        self.assertEqual(variant_card.options(self.t), ['game', 'red', 'base'])
        self.assertEqual(self.t.resolve_card('c_ambassador_gold'), self.p['gold_blu'])
        variant_card.set_choice(self.t, 'red')
        self.assertEqual(self.t.resolve_card('c_ambassador_gold'), self.p['mine'])
        self.assertEqual(variant_card.build_images(self.t),
                         {'c_ambassador_gold': self.p['mine'],
                          'c_ambassador_blue_gold': self.p['mine']})
        variant_card.set_choice(self.t, 'base')
        self.assertEqual(self.t.resolve_card('c_ambassador_gold'), self.p['base_blu'])


class SharedGoldTests(VariantSourceTests):
    """Общее золото (ракетомёт): выбор на синих доходит до сборки"""

    def test_choice_on_blue_is_the_shared_one(self):
        from src.domain.preview import variant_card
        self.t.active_team = self.Team.BLU
        variant_card.set_choice(self.t, 'base')
        self.t.active_team = self.Team.RED
        self.assertEqual(variant_card.choice(self.t), 'base')
        self.assertEqual(variant_card.build_images(self.t), {'c_ambassador_gold': self.p['base']})
        self.t.active_team = self.Team.BLU
        self.assertEqual(self.t.resolve_card('c_ambassador_gold'), self.p['base'])


def test_blue_material_takes_its_red_card_settings():
    from src.data.texture_overrides import own_settings
    settings = {'c_ambassador_gold': {'size': [1024, 1024]}}
    assert own_settings(settings, 'c_ambassador_blue_gold') == {'size': [1024, 1024]}
    assert own_settings(settings, 'c_other_blue') is None


class ForcedTeamGoldTests(VariantSourceTests):
    """«Сделать командным» синит и австралий: у синих свой скин 3"""

    def test_forced_team_makes_gold_a_team_card(self):
        from src.domain.preview import variant_card
        Team = self.Team
        self.t.blu_name_map = {}
        self.t.force_team = True
        self.assertEqual(variant_card.blue_name(self.t), 'c_ambassador_gold_blue')
        self.assertTrue(self.t.is_team_material('c_ambassador_gold'))
        self.t.set_texture('c_ambassador_gold', self.p['mine'])
        self.t.active_team = Team.BLU
        self.assertEqual(variant_card.options(self.t), ['game', 'red', 'base'])
        self.t.set_texture('c_ambassador_gold', self.p['mine_blu'])
        self.assertEqual(variant_card.build_images(self.t),
                         {'c_ambassador_gold': self.p['mine'],
                          'c_ambassador_gold_blue': self.p['mine_blu']})
        variant_card.set_choice(self.t, 'game')     # синее золото в игре - как красное
        self.assertEqual(variant_card.build_images(self.t)['c_ambassador_gold_blue'],
                         self.p['gold'])


def test_force_team_rows_blue_the_australium_too():
    from src.services.qc_skin_parser import force_team_rows
    rows = [["c_claymore"], ["c_claymore"], ["c_claymore_gold"], ["c_claymore_gold"]]
    assert force_team_rows(rows, ["c_claymore"]) == [
        ["c_claymore"], ["c_claymore_blue"], ["c_claymore_gold"], ["c_claymore_gold_blue"]]
