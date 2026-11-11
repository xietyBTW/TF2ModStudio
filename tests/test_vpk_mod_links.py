"""Карточки мода связаны с мешами и командами так же, как у игрового предмета"""

import os
import tempfile

from src.app.vpk_mod_controller import VpkModController
from src.domain.preview.session import PreviewSession
from src.services import vpk_mod_models as vm
from src.shared.constants import Team


def _png() -> str:
    f = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
    f.close()
    return f.name


def test_mesh_finds_its_card_through_the_vmt():
    # Текстура шляпы названа не как материал: связь - $basetexture VMT
    vmts = {"models/player/items/all_class/paper_hat/paper_hat":
            '"VertexLitGeneric" { "$basetexture" '
            '"models/player/items/all_class/paper_hat/paper_hat_color" }'}
    links = vm.mesh_links(
        ["paper_hat"], ["models/player/items/all_class/paper_hat"], lambda p: vmts.get(p, ""),
        {"paper_hat_color":
         "console/models/player/items/all_class/paper_hat/paper_hat_color"})
    assert links == {"paper_hat": "paper_hat_color"}


def _mod_session():
    p = PreviewSession(custom_vpk_mode=True,
                       custom_model_materials=["c_gun", "festive_lights_red"])
    t = p.textures
    t.material_names = ["c_gun_color", "festive_lights_red", "festive_lights_blue"]
    red, blu, gun = _png(), _png(), _png()
    t.vpk_red_tex_map.update({"c_gun_color": gun, "festive_lights_red": red,
                              "festive_lights_blue": blu})
    VpkModController(p)._on_links({"c_gun": "c_gun_color",
                                   "festive_lights_red": "festive_lights_red"},
                                  {"festive_lights_red": "festive_lights_blue"})
    return p, red, blu, gun


def test_blue_card_is_the_blue_side_of_the_red_one():
    p, red, blu, gun = _mod_session()
    t = p.textures
    # Синей карточки в ряду нет: она показывается переключателем команды
    assert t.material_names == ["c_gun_color", "festive_lights_red"]
    assert p.has_team_variant()
    assert p.scene_textures()["festive_lights_red"] == red
    # За BLU меш красных огоньков носит синюю текстуру мода, пушка - свою
    t.active_team = Team.BLU
    assert p.scene_textures() == {"c_gun": gun, "festive_lights_red": blu}
    assert p.scene_names("c_gun_color") == ["c_gun"]
    for f in (red, blu, gun):
        os.unlink(f)


def test_blue_edit_goes_to_the_blue_file_in_the_build():
    p, *files = _mod_session()
    t = p.textures
    mine_red, mine_blu = _png(), _png()
    t.set_texture("festive_lights_red", mine_red)
    t.active_team = Team.BLU
    t.set_texture("festive_lights_red", mine_blu)
    assert t.mod_uploads() == {"festive_lights_red": mine_red,
                               "festive_lights_blue": mine_blu}
    for f in (*files, mine_red, mine_blu):
        os.unlink(f)


def test_red_edit_before_pairing_is_not_the_blue_texture():
    # Восстановленная работа: красная карточка до пары была общей и легла
    # копией и за BLU. Синий VTF мода должен остаться своим
    p = PreviewSession(custom_vpk_mode=True, custom_model_materials=["hat"])
    t = p.textures
    t.material_names = ["hat", "hat_blue"]
    mine = _png()
    t.set_texture("hat", mine)
    assert t.textures[Team.BLU]["hat"] == mine
    VpkModController(p)._on_links({"hat": "hat"}, {"hat": "hat_blue"})
    assert "hat" not in t.textures[Team.BLU]
    assert t.mod_uploads() == {"hat": mine}
    os.unlink(mine)


def test_style_keeps_unchanged_meshes():
    p, red, blu, gun = _mod_session()
    t = p.textures
    t.skin_info = {"rows": [["c_gun"], ["c_gun_gold"]]}
    t.active_skin = 1
    # Столбец пушки в стиле не менялся: остаётся база, а не пустота
    assert p.scene_textures()["c_gun"] == gun
    for f in (red, blu, gun):
        os.unlink(f)
