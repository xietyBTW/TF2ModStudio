"""Материал War Paint (глянец macaw) правкой VMT и его путь в сборке"""

from __future__ import annotations

from src.domain.preview.vmt_edits import VmtEdits
from src.services import paintkit_vmt
from src.services.edited_vmt_service import EditedVMTService
from src.services.texture_build.main_texture import _write_main_vmt

MACAW = '''"VertexLitGeneric"
{
	"$baseTexture" "models/weapons/c_models/c_scattergun/c_scattergun"
	"$phongexponent" "255"
//	"$basetexture" "commented/out"
	"$phongalbedotint" "1"
}
'''

GAME = '''"VertexLitGeneric"
{
	"$basetexture" "models/weapons/c_models/c_scattergun/c_scattergun_blue"
	"$phongexponent" "15"
}
'''


def test_compose_takes_game_basetexture_and_marks():
    text = paintkit_vmt.compose(MACAW, GAME, 'Party Phantoms')
    assert paintkit_vmt.is_war_paint(text)
    assert '"$baseTexture" "models/weapons/c_models/c_scattergun/c_scattergun_blue"' in text
    assert '"$phongexponent" "255"' in text
    # Закомментированная строка - не параметр, её не трогаем
    assert '//\t"$basetexture" "commented/out"' in text


def test_compose_one_line_ending():
    text = paintkit_vmt.compose(MACAW.replace('\n', '\r\n'), GAME, 'x')
    assert '\r' not in text


def test_compose_without_game_texture_gives_none():
    assert paintkit_vmt.compose(MACAW, '"VertexLitGeneric" {}', 'x') is None


def test_human_edit_is_not_war_paint():
    assert not paintkit_vmt.is_war_paint(GAME)
    assert not paintkit_vmt.is_war_paint(None)


def test_build_points_war_paint_vmt_at_mod_texture(tmp_path):
    game_vmt = tmp_path / 'game.vmt'
    game_vmt.write_text(GAME, encoding='utf-8')
    out = tmp_path / 'out.vmt'
    edit = paintkit_vmt.compose(MACAW, GAME, 'Party Phantoms')
    with EditedVMTService.use(VmtEdits({'c_scattergun_blue': edit}, {})):
        _write_main_vmt(str(game_vmt), out, 'c_scattergun_blue',
                        'console/models/weapons/c_models/c_scattergun', 'scout_c_scattergun',
                        True, None, False)
    built = out.read_text(encoding='utf-8')
    assert '"$phongexponent" "255"' in built
    assert 'console/models/weapons/c_models/c_scattergun/c_scattergun_blue' in built
