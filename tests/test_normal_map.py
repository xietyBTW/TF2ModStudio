"""
Карта нормалей: маска блеска и родная нормаль (src/services/normal_map.py)

Две ошибки, которые видны только в игре. У материала с `$phong` и
`$basemapalphaphongmask` шейдер нормаль не читает (Source SDK 2013,
skin_ps20b.fxc) - рельеф не появлялся вовсе. А ресайз родной нормали через
RGBA обнулял её там, где маска блеска равна нулю
"""

from unittest import mock

import numpy as np
import pytest
from PIL import Image

from src.services import normal_map
from src.services.normal_map import NormalSettings
from src.services.texture_service import TextureService

PHONG = ('"VertexLitGeneric"\n{\n\t"$basetexture" "models/w/gun"\n'
         '\t"$phong" "1"\n\t"$basemapalphaphongmask" "1"\n}\n')


def _vmt(*lines):
    return '"VertexLitGeneric"\n{\n' + ''.join(f'\t{line}\n' for line in lines) + '}\n'


def test_stock_normal_survives_resize_where_its_alpha_is_zero():
    """Маска блеска ноль - не прозрачность: нормаль под ней обязана уцелеть"""
    stock = np.zeros((8, 8, 4), np.uint8)
    stock[..., :3] = (128, 128, 255)
    stock[:, 4:, 3] = 255                      # левая половина маски - ноль
    flat = np.full((32, 32, 3), 128, np.uint8)

    out = normal_map.make(flat, NormalSettings(), stock)
    assert out[..., 2].min() >= 250, "нормаль ушла под поверхность"
    assert (out[:, :12, 3] == 0).all() and (out[:, 20:, 3] == 255).all()


def test_steep_relief_on_a_steep_stock_never_points_under_the_surface():
    steep = np.zeros((8, 8, 3), np.float32)
    steep[...] = (0.94, 0.0, 0.34)                    # 70° в одну сторону
    out = normal_map.blend(steep, steep.copy())
    assert out[..., 2].min() >= 0.0
    assert np.allclose(np.linalg.norm(out, axis=2), 1.0, atol=1e-4)


def test_fit_resizes_every_channel_on_its_own():
    rgba = np.zeros((4, 4, 4), np.uint8)
    rgba[..., :3] = 200
    big = normal_map.fit(rgba, 8, 8)
    assert big.shape == (8, 8, 4)
    assert (big[..., :3] == 200).all() and (big[..., 3] == 0).all()
    assert normal_map.fit(rgba, 4, 4) is rgba


@pytest.mark.parametrize('text, expected', [
    (PHONG, True),
    (_vmt('"$phong" "1"'), False),
    (_vmt('"$basemapalphaphongmask" "1"'), False),                       # без phong шейдер другой
    (_vmt('"$phong" "1"', '"$basemapalphaphongmask" "0"'), False),
    (_vmt('"$phong" "1"', '// "$basemapalphaphongmask" "1"'), False),    # закомментирован
    # Прозрачному параметр снимать нельзя: альфа основы стала бы прозрачностью
    (_vmt('"$phong" "1"', '"$basemapalphaphongmask" "1"', '"$translucent" "1"'), False),
    (_vmt('"$phong" "1"', '"$basemapalphaphongmask" "1"', '"$alphatest" "1"'), False),
    # Здесь альфа основы занята краской и в прозрачность не идёт
    (_vmt('"$phong" "1"', '"$basemapalphaphongmask" "1"', '"$translucent" "1"',
          '"$blendtintbybasealpha" "1"'), True),
    ('', False), (None, False),
])
def test_phong_mask_in_base(text, expected):
    assert normal_map.phong_mask_in_base(text) is expected


def test_options_get_the_mask_flag_only_with_normal_on():
    assert normal_map.options_for(PHONG, {'normal': True})[normal_map.MASK_FROM_BASE] is True
    assert normal_map.MASK_FROM_BASE not in normal_map.options_for(PHONG, {'normal': False})
    assert normal_map.MASK_FROM_BASE not in normal_map.options_for(_vmt('"$phong" "1"'),
                                                                   {'normal': True})
    assert normal_map.options_for(PHONG, None) == {}
    assert NormalSettings.from_options(
        normal_map.options_for(PHONG, {'normal': True})).mask_from_base is True


def test_mask_from_base_puts_the_picture_alpha_into_the_normal():
    rgba = np.full((16, 16, 4), 128, np.uint8)
    rgba[..., 3] = np.tile(np.arange(16, dtype=np.uint8) * 16, (16, 1))
    settings = NormalSettings(mask_from_base=True)

    assert (normal_map.make(rgba, settings)[..., 3] == rgba[..., 3]).all()
    # Картинка без альфы в игре блестит целиком - так и остаётся
    assert (normal_map.make(rgba[..., :3], settings)[..., 3] == 255).all()
    # Без флага альфа картинки не при чём
    assert (normal_map.make(rgba, NormalSettings())[..., 3] == 255).all()
    # Маска основы важнее альфы родной нормали
    stock = np.full((16, 16, 4), 7, np.uint8)
    stock[..., :3] = (128, 128, 255)
    assert (normal_map.make(rgba, settings, stock)[..., 3] == rgba[..., 3]).all()


def test_normal_png_keeps_the_mask_of_the_picture(tmp_path):
    src = tmp_path / 'base.png'
    rgba = np.full((16, 16, 4), 90, np.uint8)
    rgba[:, :8, 3] = 0
    rgba[:, 8:, 3] = 255
    Image.fromarray(rgba, 'RGBA').save(src)
    out = tmp_path / 'base_normal.png'

    TextureService.write_normal_png(src, out, NormalSettings(mask_from_base=True))
    with Image.open(out) as img:
        got = np.asarray(img.convert('RGBA'))
    assert (got[:, :8, 3] == 0).all() and (got[:, 8:, 3] == 255).all()
    assert got[..., 2].min() >= 250


def test_take_phong_mask_removes_the_param_once(tmp_path):
    vmt = tmp_path / 'gun.vmt'
    vmt.write_text(PHONG, encoding='utf-8')
    assert normal_map.take_phong_mask(vmt) is True
    text = vmt.read_text(encoding='utf-8')
    assert 'basemapalphaphongmask' not in text and '"$phong" "1"' in text
    assert normal_map.take_phong_mask(vmt) is False

    glass = tmp_path / 'glass.vmt'
    glass.write_text(_vmt('"$phong" "1"', '"$basemapalphaphongmask" "1"',
                          '"$translucent" "1"'), encoding='utf-8')
    assert normal_map.take_phong_mask(glass) is False
    assert 'basemapalphaphongmask' in glass.read_text(encoding='utf-8')
    assert normal_map.take_phong_mask(tmp_path / 'missing.vmt') is False


def test_a_stock_normal_the_game_never_draws_is_not_a_base():
    """Рельеф поверх такой нормали показал бы то, чего в игре на предмете нет"""
    text = _vmt('"$phong" "1"', '"$basemapalphaphongmask" "1"', '"$bumpmap" "models/w/gun_n"')
    with mock.patch('src.services.game_vpk_reader.GameVpkReader') as reader:
        assert normal_map.stock_normal(text, ['tf2_textures_dir.vpk']) is None
    reader.assert_not_called()


def test_main_vmt_loses_the_param_when_the_normal_is_added(tmp_path):
    from src.services.texture_build import main_texture

    game = tmp_path / 'game.vmt'
    game.write_text(PHONG, encoding='utf-8')
    out = tmp_path / 'out' / 'gun.vmt'
    out.parent.mkdir()
    with mock.patch('src.services.edited_vmt_service.EditedVMTService.get_edited_vmt',
                    return_value=None):
        assert normal_map.phong_mask_in_base(main_texture._vmt_text('gun', str(game)))
        main_texture._write_main_vmt(str(game), out, 'gun', 'models/w', 'scout_gun',
                                     False, None, True)
        text = out.read_text(encoding='utf-8')
        assert '"$bumpmap" "models/w/gun_normal"' in text
        assert 'basemapalphaphongmask' not in text

        # Без галки Normal Map материал остаётся как в игре
        main_texture._write_main_vmt(str(game), out, 'gun', 'models/w', 'scout_gun',
                                     False, None, False)
        assert 'basemapalphaphongmask' in out.read_text(encoding='utf-8')
