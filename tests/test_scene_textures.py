"""Общий поиск текстур сцены: первая найденная папка выигрывает, мод - первым"""

from src.services import scene_textures


class _Resolver:
    def __init__(self, found):
        self.found = found              # {папка: {имя: png}}
        self.asked = []

    def texture_map(self, names, cdmaterials):
        self.asked.append((list(names), list(cdmaterials)))
        got = self.found.get(cdmaterials[0], {}) if cdmaterials else {}
        return {n: got.get(n) for n in names}

    def render_map(self, names, cdmaterials):
        return {n: {'cd': cdmaterials[0]} for n in names if n in self.found.get(cdmaterials[0], {})}


def test_found_once_searched_in_part_folders_in_order():
    r = _Resolver({"models/hat": {"hat": "hat.png"},
                   "models/player": {"hat": "wrong.png", "scout": "scout.png"}})
    textures, hints = scene_textures.resolve(
        r, [(["hat", "scout"], ["models/hat"]), (["hat", "scout"], ["models/player"])])
    assert textures == {"hat": "hat.png", "scout": "scout.png"}
    assert hints == {"hat": {"cd": "models/hat"}, "scout": {"cd": "models/player"}}
    # Найденное второй раз не ищется
    assert r.asked[1][0] == ["scout"]


def test_mod_files_come_first():
    assert scene_textures.archives("mod.vpk", "tex.vpk", "misc.vpk") == [
        "mod.vpk", "tex.vpk", "misc.vpk"]
    assert scene_textures.archives("", "tex.vpk", "misc.vpk") == ["tex.vpk", "misc.vpk"]
