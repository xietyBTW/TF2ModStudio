"""Пути игры как ключи: одно правило для превью, сборки и модов"""

from src.services.game_vpk_reader import texture_path
from src.services.mod_textures import texture_key as mod_key
from src.shared.game_paths import game_path, texture_key


def test_texture_key_reads_like_the_engine():
    assert texture_key('Materials\\Models\\Weapons\\C_Bat.vtf') == 'models/weapons/c_bat'
    assert texture_key('/materials/models/x/y/') == 'models/x/y'
    # Valve оставила исходное расширение в VMT праздничного Правосудия
    assert texture_key('models/workshop/weapons/c_models/c_xms_justice_xmas.psd') == \
        'models/workshop/weapons/c_models/c_xms_justice_xmas'
    assert texture_key('models/folder.v2/tex') == 'models/folder.v2/tex'


def test_every_copy_is_the_same_rule():
    assert texture_path is texture_key and mod_key is texture_key


def test_game_path():
    assert game_path('Models\\Player\\Spy.mdl ') == 'models/player/spy.mdl'
    assert game_path(None) == ''
