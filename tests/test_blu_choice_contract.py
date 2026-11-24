"""Контракт выбора синей: переключатель на карточке делает то, что написано,
в любом слоте (база, стиль с синей строкой, одноматериальная модель), и
сборка получает то же, что видно

Новый вид слота добавляется сюда сценарием, а не своим тестом: все правила
проверяются на нём сразу"""

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from src.domain.preview.texture_state import SINGLE_TEX_KEY, PreviewTextureState
from src.shared.constants import EXTRA_TEX_USE_GAME_ORIGINAL, EXTRA_TEX_USE_MAIN, Team

G = 'c_boxing_gloves'
GRU_ROWS = [[G], [G + '_blue'], [G + '_flames'], [G + '_flames_blue']]


class SlotContractTests(unittest.TestCase):
    def setUp(self):
        self._tmp = TemporaryDirectory()
        self.dir = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def png(self, name):
        p = self.dir / f'{name}.png'
        p.write_bytes(name.encode())
        return str(p)

    # Сценарии: (состояние, {карточка: синий материал сборки})

    def base(self):
        t = PreviewTextureState()
        t.material_names = [G]
        t.blu_name_map = {G: G + '_blue'}
        t.vpk_red_tex_map = {G: self.png('red')}
        t.vpk_blu_tex_map = {G: self.png('blu')}
        return t, {G: G + '_blue'}

    def gru(self):
        t, _ = self.base()
        t.skin_info = {'rows': GRU_ROWS, 'styles': [['GRU', 2]]}
        t.style_game_tex = {2: {G: self.png('fl_red')}, 3: {G: self.png('fl_blu')}}
        t.active_skin = 2
        return t, {G: G + '_flames_blue'}

    def gru_single(self):
        t = PreviewTextureState()
        t.material_names = [SINGLE_TEX_KEY]
        t.red_frames, t.blu_frames = [self.png('red')], [self.png('blu')]
        t.skin_info = {'rows': GRU_ROWS, 'styles': [['GRU', 2]]}
        t.style_game_tex = {2: {SINGLE_TEX_KEY: self.png('fl_red')},
                            3: {SINGLE_TEX_KEY: self.png('fl_blu')}}
        t.active_skin = 2
        return t, {SINGLE_TEX_KEY: G + '_flames_blue'}

    def scenarios(self):
        return {'base': self.base, 'gru': self.gru, 'gru_single': self.gru_single}

    @staticmethod
    def shown(t, mat, team):
        was, t.active_team = t.active_team, team
        try:
            return t.resolve_card(mat)
        finally:
            t.active_team = was

    def test_every_offered_choice_does_what_it_says(self):
        for name, make in self.scenarios().items():
            t, blue_material = make()
            t.active_team = Team.BLU
            choices = t.blu_choices()
            self.assertEqual(set(choices), set(blue_material), name)
            for mat, built in blue_material.items():
                with self.subTest(slot=name, card=mat):
                    red_view = self.shown(t, mat, Team.RED)
                    self.assertEqual(choices[mat], 'game')
                    self.assertEqual(t.resolve_card(mat), t.original_card(mat))
                    self.assertNotEqual(t.resolve_card(mat), red_view,
                                        'выбор, который ничего не меняет')
                    self.assertEqual(t.build_answer(built), EXTRA_TEX_USE_GAME_ORIGINAL)

                    t.set_blu_choice(mat, 'red')
                    self.assertEqual(t.blu_choices()[mat], 'red')
                    self.assertEqual(t.resolve_card(mat), red_view)
                    self.assertEqual(self.shown(t, mat, Team.RED), red_view)

                    # Своя красная едет и в синюю - и в кадр, и в сборку
                    t.active_team = Team.RED
                    own_red = self.png(f'{name}_own_red')
                    t.set_texture(mat, own_red)
                    t.active_team = Team.BLU
                    self.assertEqual(t.resolve_card(mat), own_red)
                    self.assertIn(t.build_answer(built), (own_red, EXTRA_TEX_USE_MAIN))

                    # Своя синяя главнее выбора, а выбор её снимает
                    own_blu = self.png(f'{name}_own_blu')
                    t.set_texture(mat, own_blu)
                    self.assertEqual(t.blu_choices()[mat], 'own')
                    self.assertTrue(t.has_upload(mat))
                    self.assertEqual(t.resolve_card(mat), own_blu)
                    self.assertEqual(t.build_answer(built), own_blu)
                    self.assertEqual(self.shown(t, mat, Team.RED), own_red)
                    t.set_blu_choice(mat, 'game')
                    self.assertEqual(t.blu_choices()[mat], 'game')
                    self.assertFalse(t.has_upload(mat))
                    self.assertEqual(t.resolve_card(mat), t.original_card(mat))

    def test_every_build_name_finds_the_slot_its_edit_lives_in(self):
        """Сборка спрашивает материалы строк по их именам: каждое имя
        приводит ровно в тот слот, куда правку кладёт карточка"""
        for name, make in self.scenarios().items():
            t, _ = make()
            card = t.material_names[0]
            expected = {G: (card, 0, Team.RED), G + '_blue': (card, 0, Team.BLU)}
            if t.skin_info:
                expected.update({G + '_flames': (card, 2, Team.RED),
                                 G + '_flames_blue': (card, 3, Team.BLU)})
            for material, slot in expected.items():
                with self.subTest(slot=name, material=material):
                    self.assertEqual(t.build_slot(material), slot)
                    team, row = slot[2], slot[1]
                    t.active_team = team
                    own = self.png(f'{name}_{material}')
                    if row:
                        t.skin_overrides.setdefault(row, {})[card] = own
                    else:
                        t.textures[team][card] = own
                    self.assertEqual(t.build_answer(material), own)

    def test_own_material_wins_over_someones_blue_name(self):
        """Синее имя корпуса - своя линза: правка линзы остаётся линзе"""
        t = PreviewTextureState()
        t.material_names = ['hat_red', 'lens_blue']
        t.blu_name_map = {'hat_red': 'lens_blue', 'lens_blue': 'lens_blue'}
        lens = self.png('lens')
        t.textures[Team.RED]['lens_blue'] = lens
        self.assertEqual(t.build_slot('lens_blue'), ('lens_blue', 0, Team.RED))
        self.assertEqual(t.build_answer('lens_blue'), lens)

    def test_festive_blue_does_not_take_the_plain_blue(self):
        t = PreviewTextureState()
        t.textures[Team.BLU]['c_x'] = self.png('blu')
        self.assertIsNone(t.uploaded_for_mat('c_x_blue_xmas'))
        self.assertEqual(t.uploaded_for_mat('c_x_blue'), t.textures[Team.BLU]['c_x'])

    def test_own_model_styles_have_no_blue_row(self):
        """Своя модель собирает стили сама: синей строки по именам у неё нет"""
        t, _ = self.gru()
        t.pair_styles = lambda: False
        t.active_team = Team.BLU
        self.assertEqual(t.style_row, 2)
        self.assertEqual(t.blu_choices(), {})

    def test_style_choice_is_its_own(self):
        """«Как красная» у базы не трогает стиль, и наоборот"""
        t, _ = self.gru()
        t.active_team = Team.BLU
        t.set_blu_choice(G, 'red')
        t.active_skin = 0
        self.assertEqual(t.blu_choices(), {G: 'game'})
        self.assertEqual(t.resolve_card(G), t.vpk_blu_tex_map[G])

    def test_style_without_blue_row_offers_nothing(self):
        """У Баккары синяя строка та же, что красная: выбирать нечего"""
        t, _ = self.base()
        t.skin_info = {'rows': [[G], [G + '_blue'], [G + '_b'], [G + '_b']]}
        t.style_game_tex = {2: {G: self.png('baccara')}}
        t.active_skin, t.active_team = 2, Team.BLU
        own = self.png('own_style')
        t.skin_overrides = {2: {G: own}}
        self.assertEqual(t.blu_choices(), {})
        t.set_blu_choice(G, 'game')
        self.assertEqual(t.skin_overrides[2][G], own, 'правка стиля пропала')
        self.assertEqual(t.resolve_card(G), self.shown(t, G, Team.RED))

    def test_paint_base_is_what_the_card_shows(self):
        """Основа мазков = показ без своей картинки, в любом слоте"""
        for name, make in self.scenarios().items():
            t, blue_material = make()
            t.active_team = Team.BLU
            for mat in blue_material:
                for choice in ('game', 'red'):
                    t.set_blu_choice(mat, choice)
                    with self.subTest(slot=name, choice=choice):
                        self.assertEqual(t.underlay(mat, t.style_row, Team.BLU),
                                         t.resolve_card(mat))


if __name__ == '__main__':
    unittest.main()
