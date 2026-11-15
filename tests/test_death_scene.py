"""
Сцена спец-режимов: солдат умирает нужной смертью

Крит и эффекты смерти показывают настоящую модель класса с настоящей
анимацией смерти из `soldier_animations.mdl`, и держать надо
две вещи: какому режиму какая смерть досталась и кому текстуры персонажа
вообще не нужны
"""

from __future__ import annotations

import unittest

from src.data.weapons import SPECIAL_MODES
from src.services import death_scene_worker as dsw


class SequenceTests(unittest.TestCase):

    def test_every_special_mode_has_a_scene(self):
        self.assertEqual(sorted(dsw.SEQUENCES), sorted(SPECIAL_MODES))

    def test_ice_and_gold_share_the_backstab(self):
        """Золотая статуя и ледяная - это застывшее тело, смерть одна"""
        self.assertEqual(dsw.SEQUENCES['death_ice'],
                         dsw.SEQUENCES['death_gold'])

    def test_crit_dies_of_a_headshot(self):
        self.assertEqual(dsw.SEQUENCES['critHIT'], 'primary_death_headshot')

    def test_burning_is_not_a_death_at_all(self):
        """Горящий игрок жив: стоит с оружием и вздрагивает от каждого тика
        урона. Стойка и вздрагивание в игре лежат порознь, и второе - разность
        (в SMD нули вместо поз), поэтому кладётся слоем поверх первой"""
        self.assertEqual(dsw.SEQUENCES['death_fire'], 'stand_PRIMARY')
        self.assertEqual(dsw.LAYERS['death_fire'], 'a_flinch01')
        self.assertNotIn('critHIT', dsw.LAYERS)


class FreezeTests(unittest.TestCase):
    """Где игра замораживает тело, там превью обязано показать статую"""

    def test_only_ice_and_gold_freeze(self):
        """Спайсикл и золотая сковорода не дают жертве упасть куклой: она
        доигрывает свою смерть и застывает. У горения и крита такого нет"""
        self.assertEqual(sorted(dsw.FROZEN), ['death_gold', 'death_ice'])

    def test_pause_is_longer_than_the_death_itself(self):
        """Смерть от удара в спину - чуть больше секунды. Если держать позу
        меньше, статую в кадре не разглядеть"""
        self.assertGreater(dsw.STATUE_HOLD, 2.0)

    def test_body_freezes_before_the_fall_ends(self):
        """Статуя стоит там, где тело было в тот миг

        Дай падению доиграть - и вместо статуи на земле лежит солдат
        """
        self.assertLess(dsw.FREEZE_AT, dsw.DEATH_SECONDS)


class MaterialTests(unittest.TestCase):
    """Кому текстуры персонажа доставать, а кому они лягут поверх"""

    def _emitted(self, mode: str):
        worker = dsw.DeathScenePreviewWorker.__new__(
            dsw.DeathScenePreviewWorker)
        worker.mode = mode
        sent = []
        worker.animated_ready = _Spy(sent, 'scene')
        worker.multi_material = _Spy(sent, 'textures')
        worker.render_hints = _Spy(sent, 'hints')
        worker._preview_dir = ''
        worker._emit_scene(None, {'parts': []}, '')
        return [name for name, _ in sent]

    def test_statue_skips_the_players_own_textures(self):
        """Лёд и золото ЗАМЕНЯЮТ материалы трупа целиком

        Родные текстуры под ними не видны, а их поиск - лишняя работа и гонка
        за то, какая картинка ляжет последней
        """
        for mode in dsw.FROZEN:
            self.assertEqual(self._emitted(mode), ['scene'], mode)

    def test_burning_player_keeps_his_own_textures(self):
        """Огонь в игре - слой поверх раскраски, а не замена: солдату его
        текстуры нужны так же, как в сцене крита"""
        self.assertEqual(self._emitted('death_fire'), self._emitted('critHIT'))
        self.assertIn('hints', self._emitted('death_fire'))


class FireSheetTests(unittest.TestCase):
    """Кадры игрового огня едут вьюверу одним листом"""

    def test_frames_are_laid_out_row_by_row(self):
        import os
        import tempfile
        from unittest.mock import patch

        from PIL import Image

        from src.services import special_scene_service as scene

        frames = [bytes([i * 40, 0, 0, 255]) * 4 for i in range(5)]   # 2x2 каждый
        vtf = os.path.join(tempfile.mkdtemp(), 'fire.vtf')
        open(vtf, 'wb').close()
        with patch.object(scene, '_game_vtf_file', return_value=vtf), \
             patch('src.services.vtflib_wrapper.VTFLib.read_vtf_all_frames',
                   return_value=(frames, 2, 2)):
            sheet = scene.fire_overlay(['misc.vpk'])

        self.assertEqual((sheet['cols'], sheet['rows'], sheet['count']), (3, 2, 5))
        self.assertEqual((sheet['fps'], sheet['scale']), (30, 5))
        with Image.open(sheet['atlas']) as img:
            self.assertEqual(img.size, (6, 4))
            self.assertEqual([img.getpixel(xy)[0] for xy in
                              ((0, 0), (2, 0), (4, 0), (0, 2), (2, 2))],
                             [0, 40, 80, 120, 160])
            self.assertEqual(img.getpixel((4, 2)), (0, 0, 0, 0))    # пустая клетка
        self.assertFalse(os.path.exists(vtf), "временный VTF убран")

    def test_no_game_texture_means_no_sheet(self):
        from unittest.mock import patch

        from src.services import special_scene_service as scene

        with patch.object(scene, '_game_vtf_file', return_value=''):
            self.assertEqual(scene.fire_overlay(['misc.vpk']), {})


class _Spy:
    def __init__(self, log, name):
        self._log, self._name = log, name

    def emit(self, value):
        self._log.append((self._name, value))


if __name__ == '__main__':
    unittest.main()
