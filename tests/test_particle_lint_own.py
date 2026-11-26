"""Проверка частиц перед сборкой ругается только на правки человека

Игровой огонь горящего игрока скрыт от его камеры нарочно: окно «Исправить и
собрать» не должно предлагать это «чинить» в нетронутом эффекте
"""

from src.app.particles_editor import _touched

CAMERA = (None, 0, "control point to disable rendering if it is the camera", "integer")


def _entry(status, attrs=(), modules=None):
    return {"status": status, "attrs": list(attrs), "modules": modules or {}}


def test_untouched_system_is_not_checked():
    assert not _touched(_entry("same"), CAMERA)


def test_other_edit_in_the_system_does_not_blame_valve_value():
    assert not _touched(_entry("changed", attrs=["max_particles"]), CAMERA)


def test_own_edit_of_the_attribute_is_checked():
    assert _touched(_entry("changed", attrs=[CAMERA[2]]), CAMERA)


def test_new_system_and_general_findings_are_checked():
    assert _touched(_entry("added"), CAMERA)
    assert _touched(None, None)


def test_module_attribute_follows_the_module_diff():
    fix = ("emitters", 1, "emission_rate", "float")
    assert _touched(_entry("changed", modules={"emitters": {1: {"status": "changed",
                                                                "attrs": ["emission_rate"]}}}), fix)
    assert not _touched(_entry("changed", modules={"emitters": {0: {"status": "changed",
                                                                    "attrs": ["emission_rate"]}}}), fix)
    assert _touched(_entry("changed", modules={"emitters": {1: {"status": "added", "attrs": []}}}), fix)
