"""
Запас собранных частей сцены (viewmodel_animation._remembered)

Часть оружия дописывают носителем и гирляндой прямо в её списки, поэтому
запас обязан отдавать копию: иначе носитель одной сцены остался бы в части
для следующей
"""

import os

from src.services import viewmodel_animation as vma


def _part():
    return {"kind": "weapon", "materials": ["gun"],
            "positions": [0.0, 1.5, 2.25], "normals": [0.0, 0.0, 1.0],
            "uvs": [0.5, 0.25], "skinIndex": [3, 0, 0, 0],
            "skinWeight": [1.0, 0.0, 0.0, 0.0],
            "groups": [{"material": "gun", "start": 0, "count": 1}]}


def test_second_request_does_not_build_again():
    calls = []

    def build():
        calls.append(1)
        return _part()

    first = vma._remembered(("k",), build)
    second = vma._remembered(("k",), build)
    assert len(calls) == 1
    assert second == first == _part()


def test_changing_a_part_does_not_spoil_the_kept_one():
    for _ in range(2):       # и собранная, и взятая из запаса
        part = vma._remembered(("k",), _part)
        part["positions"].extend([9.0, 9.0, 9.0])
        part["materials"].append("carrier")
        part["groups"].append({"material": "carrier", "start": 1, "count": 1})
        part["groups"][0]["start"] = 7
    assert vma._remembered(("k",), _part) == _part()


def test_without_a_key_nothing_is_kept():
    calls = []
    for _ in range(2):
        vma._remembered(None, lambda: calls.append(1) or _part())
    assert len(calls) == 2


def test_failed_build_is_not_kept():
    assert vma._remembered(("k",), lambda: None) is None
    assert vma._remembered(("k",), _part) == _part()


def test_key_follows_the_file(tmp_path):
    smd = tmp_path / "a.smd"
    smd.write_text("one")
    rig = vma._stamp([str(smd)])
    before = vma._part_key("weapon", rig, [str(smd)], ("bone",))
    assert before == vma._part_key("weapon", rig, [str(smd)], ("bone",))
    assert before != vma._part_key("weapon", rig, [str(smd)], ("other",))

    smd.write_text("another model")
    os.utime(smd, ns=(1, 1))
    assert before != vma._part_key("weapon", rig, [str(smd)], ("bone",))
    assert vma._part_key("weapon", rig, [str(tmp_path / "missing.smd")], None) is None
    assert vma._part_key("weapon", None, [str(smd)], None) is None


def test_old_parts_are_dropped():
    for i in range(vma._PARTS_MAX + 3):
        vma._remembered(("k", i), _part)
    assert len(vma._parts) == vma._PARTS_MAX
    assert ("k", 0) not in vma._parts
