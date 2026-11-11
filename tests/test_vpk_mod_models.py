"""Модели чужого VPK-мода: выбор, раскладка, игровая модель для перекраски"""

import pytest

from src.services import vpk_mod_models as vm


@pytest.mark.parametrize("path, kind", [
    ("models/weapons/c_models/c_scattergun/c_scattergun.mdl", "weapon"),
    ("models/weapons/c_models/c_scattergun/c_scattergun_xmas.mdl", "garland"),
    ("models/weapons/c_models/c_scout_arms.mdl", "arms"),
    ("models/player/scout.mdl", "player"),
    ("models/player/items/scout/hat.mdl", "cosmetic"),
    ("models/workshop_partner/player/items/heavy/shirt/shirt.mdl", "cosmetic"),
    ("models/weapons/w_models/w_rocket.mdl", "projectile"),
    ("models/items/medkit_large.mdl", "pickup"),
    ("models/props_gameplay/thing.mdl", "other"),
])
def test_kind_by_path(path, kind):
    assert vm.kind_of(path) == kind


def test_mod_without_models_and_textures_is_explained():
    assert vm.why_not_shown(["particles/hot.pcf", "sound/weapons/shot.wav"], "ru") == (
        "Этот мод здесь не открыть: в нём частицы, звуки и ни одной модели или текстуры")
    assert "HUD" in vm.why_not_shown(["resource/ui/hudammo.res"], "en")
    assert vm.why_not_shown(["particles/hot.pcf", "materials/effects/a.vtf"]) == ""
    assert vm.why_not_shown([]) == ""


def test_only_the_textures_of_the_shown_model():
    # Сборник: у каждой пушки свои VMT и VTF. Выбранной - только её, вместе
    # со служебными картами из её VMT и текстурой без VMT по имени материала
    # Собранный мод лежит в папке-обходе (console/), а разбор QC её убирает
    a, b = "console/models/weapons/c_models/c_gun_a", "console/models/weapons/c_models/c_gun_b"
    vmts = {
        f"materials/{a}/c_gun_a.vmt":
            f'"VertexLitGeneric" {{ "$basetexture" "{a}/a_color" "$bumpmap" "{a}/a_normal" }}',
        f"materials/{b}/c_gun_b.vmt": f'"VertexLitGeneric" {{ "$basetexture" "{b}/b_color" }}',
    }
    textures = [f"{a}/a_color", f"{a}/a_normal", f"{a}/c_gun_a_blue", f"{b}/b_color"]
    # Как в QC: обратные слэши и слэш в конце
    got = vm.textures_of(["c_gun_a", "c_gun_a_blue"],
                         ["models\\weapons\\c_models\\c_gun_a\\"], vmts, textures)
    assert got == {f"{a}/a_color", f"{a}/a_normal", f"{a}/c_gun_a_blue"}


def test_sky_faces_map_cards_onto_the_cube():
    cards = [{"name": "sky_upwardup", "vtf_path": "materials/skybox/sky_upwardup.vtf"},
             {"name": "sky_upwardside", "vtf_path": "materials/skybox/sky_upwardside.vtf"},
             {"name": "sky_upward_hdrup", "vtf_path": "materials/skybox/sky_upward_hdrup.vtf"},
             {"name": "gun", "vtf_path": "materials/models/gun.vtf"}]
    # Четыре бока стокового неба - одна текстура side; HDR-вариант запасной
    assert vm.sky_faces(cards) == {"up": "sky_upwardup", "lf": "sky_upwardside",
                                   "rt": "sky_upwardside", "ft": "sky_upwardside",
                                   "bk": "sky_upwardside"}
    assert vm.sky_faces(cards[3:]) == {}


def test_list_models_reads_a_real_vpk(tmp_path):
    import vpk

    root = tmp_path / "mod"
    for rel in ("models/weapons/c_models/c_scattergun/c_scattergun.mdl",
                "models/weapons/c_models/c_scout_arms.mdl",
                "materials/models/x.vtf"):
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        (root / rel).write_bytes(b"x")
    out = str(tmp_path / "mod.vpk")
    vpk.new(str(root)).save(out)
    got = vm.list_models(out)
    assert [(m["name"], m["kind"]) for m in got] == [("c_scattergun", "weapon"),
                                                    ("c_scout_arms", "arms")]


def test_stub_models_are_not_offered(monkeypatch):
    # Родная гирлянда, заменённая невидимым треугольником (decor_bake), -
    # не модель мода: показать и править в ней нечего
    mats = {b"stub": (["tf2sg_empty"], ["console/models/tf2sg_decor/empty/"]),
            b"gun": (["c_gun"], ["models/weapons/c_models/c_gun/"])}
    monkeypatch.setattr("src.services.mdl_mesh.materials", lambda data: mats[data])

    class Entry:
        def __init__(self, data):
            self.data = data

        def read(self):
            return self.data

    class Pak(dict):
        def __getitem__(self, key):
            return Entry(dict.__getitem__(self, key))

    pak = Pak({"models/weapons/c_models/c_gun/c_gun.mdl": b"gun",
               "models/weapons/c_models/c_gun/c_gun_festivizer.mdl": b"stub",
               "materials/models/x.vtf": b""})
    assert vm.real_models(pak) == ["models/weapons/c_models/c_gun/c_gun.mdl"]
