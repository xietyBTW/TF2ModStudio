"""План объединения модов: пересечения по путям файлов, по предметам"""

from pathlib import Path

import pytest
import vpk

from src.services import merge_plan


def _mod(tmp_path, name, files):
    root = tmp_path / f"src_{name}"
    for rel in files:
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        (root / rel).write_bytes(b"x")
    out = tmp_path / f"{name}.vpk"
    vpk.new(str(root)).save(str(out))
    return out


@pytest.mark.parametrize("path, item", [
    ("models/weapons/c_models/c_scattergun/c_scattergun.dx90.vtx", "c_scattergun"),
    ("materials/models/weapons/c_models/c_scattergun/c_scattergun.vtf", "c_scattergun"),
    ("materials/models/player/scout/scout_red.vtf", "scout"),
    ("materials/skybox/sky_upwardup.vtf", "skybox"),
    ("sound/weapons/scatter_gun_shoot.wav", "scatter_gun_shoot"),
])
def test_item_of(path, item):
    assert merge_plan.item_of(path) == item


def test_two_retextures_of_one_gun_conflict_without_models(tmp_path):
    # Модели нет ни в одном - а один всё равно перекроет другой
    tex = "materials/models/weapons/c_models/c_scattergun/c_scattergun.vtf"
    a = _mod(tmp_path, "red", [tex])
    b = _mod(tmp_path, "blue", [tex, "materials/models/player/scout/scout_red.vtf"])
    found = merge_plan.conflicts([b, a])
    assert found == [{"item": "c_scattergun", "mods": ["blue.vpk", "red.vpk"],
                      "winner": "blue.vpk", "files": 1}]


def test_one_model_at_different_paths_is_reported(tmp_path):
    a = _mod(tmp_path, "a", ["models/weapons/c_models/c_test/c_test.mdl"])
    b = _mod(tmp_path, "b", ["models/workshop_partner/weapons/c_models/c_test.mdl"])
    found = merge_plan.conflicts([a, b])
    assert found == [{"item": "c_test", "mods": ["a.vpk", "b.vpk"], "winner": "a.vpk",
                      "files": 0}]


def test_unrelated_mods_do_not_conflict(tmp_path):
    a = _mod(tmp_path, "a", ["materials/models/weapons/c_models/c_bat/c_bat.vtf"])
    b = _mod(tmp_path, "b", ["materials/skybox/sky_upwardup.vtf"])
    assert merge_plan.conflicts([a, b]) == []
    assert merge_plan.describe(a)["items"] == ["c_bat"]
