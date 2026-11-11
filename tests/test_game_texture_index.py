"""Таблица игры «текстура -> модели» и выбор модели для мода из одних текстур"""

from src.services import game_texture_index as gti


class _Entry:
    def __init__(self, data):
        self._data = data

    def read(self):
        return self._data


class _Pak(dict):
    """Как vpk.VPK: перебор путей и pak[путь].read()"""

    def __getitem__(self, key):
        return _Entry(dict.__getitem__(self, key))


def test_build_follows_the_games_links(monkeypatch):
    # Материал с полным путём не лежит в $cdmaterials - игра ищет его по
    # следующей папке, в конце по самому имени
    mats = {b"burner": (["models/weapons/c_items/c_backburn", "c_backburn_blue"],
                        ["models/weapons/c_items/", ""])}
    monkeypatch.setattr("src.services.mdl_mesh.materials", lambda data: mats[data])
    pak = _Pak({
        "models/weapons/c_models/c_backburner/c_backburner.mdl": b"burner",
        "materials/models/weapons/c_items/c_backburn.vmt":
            b'"VertexLitGeneric" { "$basetexture" "models\\weapons\\c_items\\c_backburn" '
            b'"$bumpmap" "models/weapons/c_items/c_backburn_normal" }',
        "materials/models/weapons/c_items/c_backburn_blue.vmt":
            b'"VertexLitGeneric" { "$basetexture" "models/weapons/c_items/c_backburn_blue" }',
    })
    table = gti.build(pak, '"model_player" "models/weapons/c_models/c_backburner/c_backburner.mdl"')
    mdl = "models/weapons/c_models/c_backburner/c_backburner.mdl"
    # Служебная карта тоже ведёт к модели: мод из одной нормали её меняет
    assert table["users"] == {"models/weapons/c_items/c_backburn": [mdl],
                              "models/weapons/c_items/c_backburn_normal": [mdl],
                              "models/weapons/c_items/c_backburn_blue": [mdl]}
    assert "models/weapons/c_items/c_backburn_normal" not in table["vmts"]
    assert table["items"] == [mdl]


def _table(users, items=()):
    return {"users": users, "items": list(items)}


def test_texture_name_does_not_have_to_match_the_model():
    t = _table({"models/weapons/c_items/c_backburn": ["models/weapons/c_models/c_backburner.mdl"]})
    vtf = "materials/models/weapons/c_items/c_backburn.vtf"
    assert gti.model_for([vtf], [vtf], t) == "models/weapons/c_models/c_backburner.mdl"
    # Собранный мод лежит в папке-обходе
    assert gti.model_for(["materials/console/models/weapons/c_items/c_backburn.vtf"], [], t)
    assert gti.model_for(["materials/models/nothing.vtf"], [], t) == ""


def test_the_model_painted_by_most_mod_textures_wins():
    t = _table({"models/a/red": ["models/x.mdl", "models/a/y.mdl"],
                "models/a/blue": ["models/a/y.mdl"]})
    assert gti.model_for(["materials/models/a/red.vtf", "materials/models/a/blue.vtf"],
                         ["materials/models/a/red.vtf"], t) == "models/a/y.mdl"


def test_named_like_the_texture_then_nearer_folder():
    rocket = "models/weapons/w_models/w_rocket01"
    t = _table({rocket: ["models/weapons/w_models/w_rocketlauncher.mdl",
                         "models/weapons/w_models/w_rocket.mdl"],
                "models/player/hvyweapon/hvyweapon_red": [
                    "models/workshop_partner/player/items/heavy/shirt/shirt.mdl",
                    "models/player/heavy.mdl"]},
               items=["models/weapons/w_models/w_rocketlauncher.mdl",
                      "models/workshop_partner/player/items/heavy/shirt/shirt.mdl"])
    vtf = f"materials/{rocket}.vtf"
    assert gti.model_for([vtf], [vtf], t) == "models/weapons/w_models/w_rocket.mdl"
    body = "materials/models/player/hvyweapon/hvyweapon_red.vtf"
    assert gti.model_for([body], [body], t) == "models/player/heavy.mdl"
    # Мод в папке-обходе: папки сравниваются по пути игры, а не мода
    body = "materials/console/models/player/hvyweapon/hvyweapon_red.vtf"
    assert gti.model_for([body], [body], t) == "models/player/heavy.mdl"


def test_hat_texture_shared_by_class_models():
    t = _table({"models/player/items/all_class/paper_hat/paper_hat_color": [
        "models/player/items/soldier/paper_hat.mdl", "models/player/items/scout/paper_hat.mdl"]},
        items=["models/player/items/scout/paper_hat.mdl",
               "models/player/items/soldier/paper_hat.mdl"])
    vtf = "materials/models/player/items/all_class/paper_hat/paper_hat_color.vtf"
    assert gti.model_for([vtf], [vtf], t).endswith("/paper_hat.mdl")
