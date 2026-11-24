"""
«Сделать праздничным»: гирлянда вшивается в модель оружия (decor_bake)

Проверено в игре на обрезе: вшитая гирлянда видна и мигает.
Здесь - то, что легко сломать: кости гирлянды по именам, командный столбец
скинов и то, что сборка не путает вшитую гирлянду с отдельной моделью
"""

from pathlib import Path
from types import SimpleNamespace

from src.domain.preview.session import PreviewSession
from src.services import decor_bake, decor_build
from src.services.build_request import BuildRequest
from src.services.vpk_service import VPKService

WEAPON_SMD = """version 1
nodes
  0 "weapon_bone" -1
  1 "weapon_bone_1" 0
end
skeleton
time 0
  0 0 0 0 0 0 0
  1 0 1 0 0 0 0
end
triangles
gun
  0 0 0 0 0 0 1 0 0 1 0 1.0
  0 1 0 0 0 0 1 1 0 1 0 1.0
  1 0 1 0 0 0 1 0 1 1 1 1.0
end
"""

# У гирлянды кости в другом порядке: номер 0 у неё - weapon_bone_1
GARLAND_SMD = """version 1
nodes
  0 "weapon_bone_1" -1
  1 "weapon_bone" 0
end
skeleton
time 0
  0 0 1 0 0 0 0
  1 0 0 0 0 0 0
end
triangles
lights
  0 5 5 5 0 0 1 0 0 1 0 1.0
  1 6 5 5 0 0 1 1 0 1 1 1.0
  0 5 6 5 0 0 1 0 1 1 0 1.0
end
"""


def test_garland_triangles_keep_their_bones_by_name(tmp_path):
    body, garland = tmp_path / "gun.smd", tmp_path / "lights.smd"
    body.write_text(WEAPON_SMD, encoding="utf-8")
    garland.write_text(GARLAND_SMD, encoding="utf-8")
    decor_bake.append_triangles(str(body), str(garland))
    lines = body.read_text(encoding="utf-8").splitlines()
    assert lines[-1] == "end" and lines.count("end") == 3
    tri = lines[lines.index("lights") + 1:lines.index("lights") + 4]
    # weapon_bone_1 у оружия - кость 1, weapon_bone - кость 0
    assert [row.split()[0] for row in tri] == ["1", "0", "1"]
    assert tri[0].split()[10] == "1" and tri[1].split()[10] == "0"
    assert "gun" in lines                                 # меш оружия на месте


def test_team_lights_follow_the_weapon_skin_pairs():
    weapon = [["gun", "gun_gold"], ["gun_blu", "gun_gold"], ["gun_gold", "gun_gold"]]
    garland = [["lights"], ["lights_blu"]]
    assert decor_bake.skin_rows(weapon, garland) == [
        ["gun", "gun_gold", "lights"], ["gun_blu", "gun_gold", "lights_blu"],
        ["gun_gold", "gun_gold", "lights"]]
    assert decor_bake.skin_rows([], garland) == garland      # оружие без скинов
    # Одна строка у оружия (револьвер): синему всё равно нужна своя
    assert decor_bake.skin_rows([["gun"]], garland) == [["gun", "lights"],
                                                        ["gun", "lights_blu"]]
    assert decor_bake.skin_rows(weapon, [["lights"]]) == []   # гирлянда без команд


def test_qc_gets_the_garland_folder_and_skins(tmp_path):
    qc = tmp_path / "gun.qc"
    qc.write_text('$modelname "weapons/gun.mdl"\n$body body "gun.smd"\n'
                  '$cdmaterials "vgui\\models\\gun\\"\n$cdmaterials ""\n'
                  '$texturegroup "skinfamilies"\n{\n\t{ "gun" }\n\t{ "gun_blu" }\n}\n',
                  encoding="utf-8")
    decor_bake.add_to_qc(str(qc), "vgui\\models\\tf2sg_decor\\gun_xmas",
                         [["lights"], ["lights_blu"]])
    text = qc.read_text(encoding="utf-8")
    assert '$cdmaterials "vgui\\models\\tf2sg_decor\\gun_xmas\\"' in text
    assert '$cdmaterials "vgui\\models\\gun\\"' in text
    assert '{ "gun" "lights" }' in text and '{ "gun_blu" "lights_blu" }' in text


def _editor(baked=""):
    from src.app.decor_editor import DecorEditor

    preview = PreviewSession()
    preview.decor_baked = baked
    host = SimpleNamespace(preview=preview, _shown_weapon=lambda: "c_scattergun")
    return DecorEditor(host)


def test_baked_garland_goes_to_the_build_with_every_native_emptied(monkeypatch):
    from src.services import festive_decor

    monkeypatch.setattr(festive_decor, "kinds", lambda key, root: {
        "xmas": "models/x_xmas.mdl", "festivizer": "models/x_festivizer.mdl"})
    assert _editor().builds("root") == []                     # без правок - ничего
    [entry] = _editor("xmas").builds("root")
    assert entry["kind"] == "xmas" and entry["bake"]
    assert entry["empty"] == ["models/x_xmas.mdl", "models/x_festivizer.mdl"]


def test_garland_is_recognised_by_its_light_materials():
    from src.services import festive_decor

    assert festive_decor.wears_garland(["c_scattergun", "festive_lights_red"])
    assert festive_decor.wears_garland(["models/weapons/xms_colored_lights"])
    assert not festive_decor.wears_garland(["c_scattergun", "c_scattergun_blue"])
    assert not festive_decor.wears_garland([])


def _mod_editor(materials, kind="weapon"):
    from src.app.decor_editor import DecorEditor

    preview = PreviewSession()
    preview.custom_vpk_mode = True
    preview.custom_vpk_kind = kind
    preview.custom_model_materials = list(materials)
    host = SimpleNamespace(preview=preview, _shown_weapon=lambda: "c_scattergun",
                           tf2_paths=lambda: {"root": "root"})
    return DecorEditor(host)


def test_mod_with_its_own_garland_empties_the_natives(monkeypatch):
    """Чужой мод с вшитой гирляндой: у праздничного оружия их было бы две"""
    from src.services import festive_decor

    monkeypatch.setattr(festive_decor, "kinds", lambda key, root: {
        "xmas": "models/x_xmas.mdl", "festivizer": "models/x_festivizer.mdl"})
    worn = _mod_editor(["c_scattergun", "festive_lights_red"])
    assert worn.builds("root") == [{"kind": "", "mdl": "", "textures": {},
                                    "empty": ["models/x_xmas.mdl", "models/x_festivizer.mdl"]}]
    # Родная гирлянда в превью повисла бы второй поверх вшитой
    assert worn.festive_options() == []

    plain = _mod_editor(["c_scattergun"])
    assert plain.builds("root") == []
    assert plain.festive_options() == ["xmas", "festivizer"]

    # Мод перекрашивает саму гирлянду: огоньки те же, но пустышкой стала бы она
    garland = _mod_editor(["festive_lights_red", "festivizer_battery"], kind="garland")
    assert garland.builds("root") == []


def test_custom_mod_build_empties_natives_and_says_so(monkeypatch, tmp_path):
    from src.services import decor_bake as bake
    from src.services.custom_vpk_service import CustomVPKService

    ctx = SimpleNamespace(vpkroot_dir=tmp_path)
    made = []
    monkeypatch.setattr(bake, "build_empty", lambda ctx, mdl, **kw: made.append(mdl))
    entries = [{"kind": "", "mdl": "", "empty": ["a.mdl", "b.mdl"]}]
    note = CustomVPKService._empty_native_decor(ctx, entries, "", "", "", "", "en")
    assert made == ["a.mdl", "b.mdl"]
    assert "removed" in note

    # Своя гирлянда автора мода остаётся его работой
    made.clear()
    (tmp_path / "a.mdl").write_bytes(b"IDST")
    CustomVPKService._empty_native_decor(ctx, entries, "", "", "", "", "en")
    assert made == ["b.mdl"]

    def broken(ctx, mdl, **kw):
        raise FileNotFoundError(mdl)

    monkeypatch.setattr(bake, "build_empty", broken)
    assert "two" in CustomVPKService._empty_native_decor(ctx, entries, "", "", "", "", "en")
    assert CustomVPKService._empty_native_decor(ctx, [{"mdl": "m"}], "", "", "", "", "en") == ""


def test_build_keeps_the_weapon_and_skips_the_baked_garland_model():
    baked = [{"kind": "xmas", "mdl": "m", "bake": True, "textures": {}}]
    assert not VPKService._is_decor_only(BuildRequest(decor_builds=baked))
    assert VPKService._is_decor_only(BuildRequest(
        decor_builds=[{"kind": "xmas", "mdl": "m", "textures": {}}]))
    ctx = SimpleNamespace(temp_dir=str(Path(".")), vpkroot_dir=Path("."))
    assert decor_build.build_decor_models(
        ctx, baked, misc_vpk="", textures_vpk="", studiomdl_exe="", tf_dir="",
        size=(4, 4), format_type="DXT5", flags=[], vtf_options={}) == 0


def test_baked_kind_lives_in_the_work():
    p = PreviewSession()
    p.decor_baked = "festivizer"
    edits = p.user_edits()
    q = PreviewSession()
    q.apply_user_edits(edits)
    assert q.decor_baked == "festivizer"
