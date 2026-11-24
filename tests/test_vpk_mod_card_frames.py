"""
Анимированные текстуры чужого мода: огоньки вшитой гирлянды

Раньше на кадры раскладывалась только главная текстура мода, и её кадры
ложились на все меши разом. Огоньки - отдельный материал с многокадровым
VTF, и в превью они стояли. Крутится только то, что крутит сама игра:
многокадровый VTF без прокси AnimatedTexture в игре стоит на первом кадре
"""

import io
import tempfile
import unittest

from src.app.vpk_mod_controller import VpkModController
from src.domain.preview.session import PreviewSession
from src.services import vpk_mod_cards

_BLINKING = ('"VertexLitGeneric" { "$basetexture" "lights" "Proxies" { '
             '"AnimatedTexture" { "animatedtexturevar" "$basetexture" '
             '"animatedtextureframenumvar" "$frame" '
             '"animatedtextureframerate" "1" } } }')
_STILL = '"VertexLitGeneric" { "$basetexture" "lights" }'


def _vtf(frames: int) -> bytes:
    from srctools.vtf import VTF, ImageFormats
    vtf = VTF(16, 16, fmt=ImageFormats.RGBA8888, frames=frames)
    for i in range(frames):
        vtf.get(frame=i).copy_from(bytes([60 * i, 0, 0, 255]) * 256)
    buf = io.BytesIO()
    vtf.save(buf)
    return buf.getvalue()


class CardFramesTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()

    def tearDown(self):
        self._tmp.cleanup()

    def test_blinking_lights_are_laid_out_frame_by_frame(self):
        got = vpk_mod_cards.frames(_vtf(3), 'lights', _BLINKING, self._tmp.name)
        self.assertIsNotNone(got)
        paths, fps = got
        self.assertEqual(len(paths), 3)
        self.assertEqual(fps, 1.0)

    def test_frames_without_the_proxy_stand_still_like_in_game(self):
        self.assertIsNone(vpk_mod_cards.frames(_vtf(3), 'lights', _STILL, self._tmp.name))

    def test_one_frame_is_not_an_animation(self):
        self.assertIsNone(vpk_mod_cards.frames(_vtf(1), 'lights', _BLINKING, self._tmp.name))

    def test_texture_only_mod_takes_the_proxy_from_the_game_vmt(self):
        """У мода из одних текстур VMT игровой - прокси живёт в нём"""
        from unittest.mock import patch
        card = {'name': 'lights', 'vtf_path': 'materials/x/lights.vtf', 'vmt_path': None}
        pak = {'materials/x/lights.vtf': io.BytesIO(_vtf(3))}
        with patch.object(vpk_mod_cards, 'game_vmt_text', return_value=_BLINKING), \
                patch.object(vpk_mod_cards.game_texture_index, 'load', return_value={}), \
                patch.object(vpk_mod_cards.game_texture_index, 'vmt_for',
                             return_value='materials/x/lights.vmt'):
            vpk_mod_cards.animate([card], pak, {}, 'misc.vpk', self._tmp.name)
        self.assertEqual(len(card['frames']), 3)

    def test_frames_get_the_same_tint_as_the_still(self):
        from unittest.mock import patch
        with patch('src.services.vmt_tint.apply_to_png') as tinted:
            paths, _ = vpk_mod_cards.frames(_vtf(3), 'lights', _BLINKING, self._tmp.name)
        self.assertEqual([c.args[0] for c in tinted.call_args_list], paths)

    def test_frame_count_comes_from_the_header(self):
        self.assertEqual(vpk_mod_cards.vtf_frame_count(_vtf(3)), 3)
        self.assertEqual(vpk_mod_cards.vtf_frame_count(b'not a vtf'), 1)


class GameMeshesTests(unittest.TestCase):
    """Мод ссылается на игровую текстуру огоньков: карточки у неё нет, а
    меш всё равно должен получить свою текстуру и мигать, как в игре"""

    def test_lights_take_the_game_texture_and_blink(self):
        vmts = {'materials/console/x/festive_lights_red.vmt':
                _BLINKING.replace('"lights"', '"models/game/festive_lights"')}
        asked = []

        def vtf(base):
            asked.append(base)
            return _vtf(3) if base == 'models/game/festive_lights' else None

        with tempfile.TemporaryDirectory() as tmp:
            found = vpk_mod_cards.game_meshes(
                '', ['c_gun', 'festive_lights_red', 'no_vmt'], {'c_gun': 'c_gun'},
                vmts, '', vtf, tmp)
        self.assertEqual(sorted(found), ['festive_lights_red'])
        self.assertEqual(len(found['festive_lights_red']['frames']), 3)
        self.assertEqual(found['festive_lights_red']['fps'], 1.0)
        # Меш с карточкой мода игровую текстуру не спрашивает
        self.assertEqual(asked, ['models/game/festive_lights'])

    def test_game_texture_lies_under_the_mod_cards(self):
        session = PreviewSession()
        session.custom_vpk_mode = True
        session.custom_model_materials = ['festive_lights_red']
        session.mod_game_textures = {'festive_lights_red': 'game.png'}
        self.assertEqual(session.scene_textures(), {'festive_lights_red': 'game.png'})
        session.textures.vpk_red_tex_map['festive_lights_red'] = __file__
        self.assertEqual(session.scene_textures(), {'festive_lights_red': __file__})


class SceneAnimationsTests(unittest.TestCase):
    """Кадры ложатся только на меши своей карточки и только пока она своя"""

    def test_only_meshes_of_the_untouched_card_blink(self):
        session = PreviewSession()
        session.mod_frames = {'C:/p/_card_lights.png': {'frames': ['a', 'b'], 'fps': 1.0}}
        controller = VpkModController(session)
        scene = {'lights_mesh': 'C:/p/_card_lights.png',
                 'gun_mesh': 'C:/p/_card_gun.png',
                 # своя картинка человека поверх огоньков - уже не игровое мигание
                 'other_lights': 'C:/my/painted.png'}
        self.assertEqual(controller.animations(scene), {
            'lights_mesh': {'still': 'C:/p/_card_lights.png', 'frames': ['a', 'b'],
                            'fps': 1.0}})

    def test_new_item_forgets_the_frames(self):
        session = PreviewSession()
        session.mod_frames = {'x.png': {'frames': ['a', 'b'], 'fps': 1.0}}
        session.reset_team_frames()
        self.assertEqual(session.mod_frames, {})
