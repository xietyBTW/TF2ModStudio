"""Классы TF2: подрывник в путях моделей - `_demo`"""

from src.data.tf2_classes import CLASSES, class_of_model, model_token, strip_class, with_class
from src.services.tf2_paths import build_hat_mdl_candidates


def test_demo_token_both_ways():
    assert model_token("demoman") == "demo" and model_token("heavy") == "heavy"
    assert class_of_model("models/player/items/demo/hat_demo.mdl") == "demoman"
    assert class_of_model("hat_demoman.mdl") == "demoman"
    assert class_of_model("models/player/items/all_class/hat.mdl") is None
    assert with_class("hat_heavy.mdl", "demoman") == "hat_demo.mdl"
    assert strip_class("hat_demo") == "hat" and strip_class("hat_spy") == "hat"
    assert len(CLASSES) == 9


def test_hat_candidates_reach_the_demo_model():
    cands = build_hat_mdl_candidates("models/player/items/heavy/hat_heavy.mdl")
    assert "models/player/items/heavy/hat_demo.mdl" in cands
    assert "models/player/items/all_class/x_demo.mdl" in build_hat_mdl_candidates(
        "models/player/items/all_class/x_%s.mdl")


def test_texture_guess_expands_demo():
    from src.services.texture_locator import hat_vtf_paths
    paths = hat_vtf_paths("models/player/items/all_class/x_%s.mdl")
    assert any(p.endswith("x_demo.vtf") for p in paths)
