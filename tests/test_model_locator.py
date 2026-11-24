"""Где лежит модель предмета: один ответ по виду предмета"""

from src.data.player_characters import PLAYER_BODY_MODE_KEYS, SPY_MASK_MODE_KEY, SPY_MDL_PATH
from src.data.player_hands import HAND_MODE_KEYS, HAND_MODES
from src.services.model_locator import mdl_candidates, weapon_candidates


def test_each_kind_finds_its_model():
    hat = mdl_candidates("hat", "models/player/items/all_class/x.mdl")
    assert hat and hat[0].endswith(".mdl")
    assert mdl_candidates(SPY_MASK_MODE_KEY) == [SPY_MDL_PATH]
    body = next(iter(PLAYER_BODY_MODE_KEYS))
    assert len(mdl_candidates(body)) == 1 and mdl_candidates(body)[0].endswith(".mdl")
    hands = next(iter(HAND_MODE_KEYS))
    arm = HAND_MODES[hands]["arm_model"]
    assert mdl_candidates(hands) == weapon_candidates(hands, arm)
    assert mdl_candidates("scout_c_scattergun") == weapon_candidates("scout_c_scattergun", "c_scattergun")


def test_weapon_layouts_in_order():
    paths = weapon_candidates("scout_c_bat", "c_bat")
    assert paths[0].startswith("models/workshop_partner/")
    assert paths[-2:] == ["models/player/items/scout/c_bat/c_bat.mdl",
                          "models/player/items/scout/c_bat.mdl"]
    assert mdl_candidates("critHIT") == []
