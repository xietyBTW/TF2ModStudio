"""Австралий мода из VPK: золото, которого в моде нет, сборка дописывает"""

from src.services import mod_variant

GAME_VMT = '"VertexLitGeneric"\n{\n\t"$basetexture" "models/weapons/c_models/c_scattergun/c_scattergun_gold"\n\t"$envmap" "env_cubemap"\n}\n'
INFO = {'card': 'c_scattergun_gold', 'material': 'c_scattergun_gold', 'in_mod': False,
        'folder': 'console/ab12/models/weapons/c_models/c_scattergun', 'game_vmt': GAME_VMT}


def test_gold_goes_where_the_model_looks_with_the_game_vmt(tmp_path):
    tex = mod_variant.missing_texture(tmp_path, INFO, [{'name': 'c_scattergun'}])
    mod_variant.write_vmt(tex)
    folder = tmp_path / 'materials' / INFO['folder']
    text = (folder / 'c_scattergun_gold.vmt').read_text(encoding='utf-8')
    assert f'"{INFO["folder"]}/c_scattergun_gold"' in text      # VTF рядом, в моде
    assert '$envmap' in text                                    # блеск золота игры
    assert tex['vtf_path'] == str(folder / 'c_scattergun_gold.vtf')


def test_mod_own_gold_vmt_is_kept_and_pointed_at_the_new_vtf(tmp_path):
    own = tmp_path / 'materials' / 'models' / 'mine'
    own.mkdir(parents=True)
    (own / 'c_scattergun_gold.vmt').write_text(
        '"VertexLitGeneric"\n{\n\t$basetexture models/somewhere/else\n\t"$phong" "1"\n}\n')
    tex = mod_variant.missing_texture(tmp_path, INFO, [])
    assert tex['vmt_path'] == str(own / 'c_scattergun_gold.vmt')
    assert '"models/mine/c_scattergun_gold"' in tex['vmt_text'] and '$phong' in tex['vmt_text']


def test_nothing_to_add_when_the_mod_has_its_gold(tmp_path):
    assert mod_variant.missing_texture(tmp_path, {**INFO, 'in_mod': True}, []) is None
    assert mod_variant.missing_texture(tmp_path, INFO, [{'name': 'c_scattergun_gold'}]) is None


def test_blue_gold_is_the_blue_side_of_the_australium_card(tmp_path):
    """Синее золото мода - не своя карточка: картинка лежит синей стороной
    карточки австралия, а в сборку уходит под именем синего VTF"""
    from src.domain.preview import variant_card
    from src.domain.preview.texture_state import PreviewTextureState
    from src.shared.constants import Team

    t = PreviewTextureState()
    t.material_names = ['c_rocketlauncher']
    t.australium_mat_name, t.australium_blu_mat = 'c_rocketlauncher_gold', 'c_rocketlauncher_gold_blue'
    t.australium_frame = t.australium_blu_frame = str(tmp_path / 'gold.png')
    mine = tmp_path / 'mine.png'
    mine.write_bytes(b'png')
    t.textures.setdefault(Team.BLU, {})['c_rocketlauncher_gold'] = str(mine)

    assert variant_card.side_of(t, 'C_Rocketlauncher_Gold_Blue') == Team.BLU
    assert variant_card.side_of(t, 'c_rocketlauncher') is None
    assert t.uploaded_for_mat('c_rocketlauncher_gold_blue') == str(mine)
    assert t.mod_uploads() == {'c_rocketlauncher_gold_blue': str(mine)}


def test_australium_paints_the_meshes_its_row_replaces():
    rows = [['c_rl', 'lens'], ['c_rl_blue', 'lens'], ['c_rl_gold', 'lens']]
    assert mod_variant._replaced(rows, 'c_rl_gold') == ['c_rl']
