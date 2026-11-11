"""Мод-шапка: что мод заменяет и кого из классов показать на персонаже"""

from types import SimpleNamespace

from src.app import mod_hat
from src.domain.preview.session import PreviewSession
from src.services import vpk_mod_models as vm


def _hat(per_class, styles=(), classes=()):
    return SimpleNamespace(per_class_models=per_class, styles=list(styles),
                           classes=list(classes) or list(per_class))


def test_texture_mod_dresses_every_class():
    item = _hat({"scout": "models/player/items/scout/hat.mdl",
                 "spy": "models/player/items/spy/hat.mdl"})
    assert mod_hat.models_by_class(item, "models/player/items/spy/hat.mdl", own=False) == {
        "scout": "models/player/items/scout/hat.mdl", "spy": "models/player/items/spy/hat.mdl"}


def test_own_model_replaces_only_its_class():
    # В игре у остальных классов осталась бы игровая шапка
    item = _hat({"scout": "models/player/items/scout/hat.mdl",
                 "spy": "models/player/items/spy/hat.mdl"})
    assert mod_hat.models_by_class(item, "Models\\Player\\Items\\Scout\\hat.mdl", own=True) == {
        "scout": "models/player/items/scout/hat.mdl"}


def test_model_of_a_style_takes_the_style_models():
    item = _hat({"scout": "models/a.mdl"},
                styles=[{"per_class_models": {"scout": "models/a_style.mdl",
                                              "spy": "models/a_style.mdl"}}])
    assert mod_hat.models_by_class(item, "models/a_style.mdl", own=False) == {
        "scout": "models/a_style.mdl", "spy": "models/a_style.mdl"}


def test_one_model_for_everyone_and_no_catalog_row():
    item = _hat({}, classes=["scout", "spy"])
    assert mod_hat.models_by_class(item, "models/all.mdl", own=True) == {
        "scout": "models/all.mdl", "spy": "models/all.mdl"}
    assert mod_hat.models_by_class(None, "models/all.mdl", own=False) == {}


def test_only_a_shown_cosmetic_mod_is_a_hat():
    p = PreviewSession(custom_vpk_mode=True, custom_vpk_kind="cosmetic")
    assert mod_hat.is_hat(p)
    p.reset_custom_vpk()
    assert not mod_hat.is_hat(p)


def test_target_prefers_the_mods_own_model(monkeypatch):
    files = ["models/player/items/scout/hat.mdl", "materials/models/x/hat.vtf"]
    assert vm.target(files, {}, "", "misc.vpk") == ("models/player/items/scout/hat.mdl", True)
    # Без модели - модель игры, которая рисует текстуры
    monkeypatch.setattr("src.services.game_texture_index.load",
                        lambda _p: {"users": {"models/x/hat": ["models/player/items/spy/hat.mdl"]}})
    assert vm.target(files[1:], {}, "", "misc.vpk") == ("models/player/items/spy/hat.mdl", False)
    assert vm.target(files[1:], {}, "", "") == ("", False)
