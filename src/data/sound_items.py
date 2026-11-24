"""
Звуки и предметы игры: чей это звук, по items_game

Имя записи о классе молчит (дробовик носят четверо), а предмет знает. Две
связки: запись -> предметы и классы (из `visuals` предмета) и токен названия
предмета -> классы (для записей, нашедших имя через локализацию). Классы
всегда с учётом prefab - так их видит игра
"""

from __future__ import annotations

import re
from typing import Dict, Tuple

from src.data.tf2_classes import CLASSES

_SOUND_KEY = re.compile(r'"(sound_[a-z0-9_]+)"\s+"([^"]+)"')
_CLASS_ON = re.compile(r'"(' + '|'.join(CLASSES) + r')"\s+"1"')


def _item_classes(game, block: str) -> set:
    """Классы предмета так, как их видит игра: блок предмета, слитый с
    prefab. У Мачины, AWP и Brawler Blaster классы только в prefab, и по
    одному блоку предмета их звуки уходили в «прочие»"""
    return set(_CLASS_ON.findall(game.merged_block(block, 'used_by_classes')))


def item_bindings(items_game_text: str) -> Dict[str, Tuple[set, set]]:
    """{имя записи: (предметы, классы)} - из блоков `visuals` в items_game

    Единственное место, где сказано, ЧЕЙ это звук: имя записи о классе молчит,
    дробовик носят трое
    """
    from src.data.items_game_kv import ItemsGame

    return item_bindings_of(ItemsGame.parse(items_game_text))


def item_bindings_of(game) -> Dict[str, Tuple[set, set]]:
    """То же по разобранному items_game (`ItemsGame`)

    Звуки - из СВОЕГО блока предмета, как и раньше: звук из общего prefab
    привязал бы запись к десяткам предметов, и подпись строки поменялась бы.
    Классы - с prefab
    """
    out: Dict[str, Tuple[set, set]] = {}
    for _key, block in game.items:
        sounds = _SOUND_KEY.findall(block)
        if not sounds:
            continue
        title = (game.inherited(block, 'item_name') or '').lstrip('#')
        classes = _item_classes(game, block)
        for _event, entry in sounds:
            items, known = out.setdefault(entry, (set(), set()))
            if title:
                items.add(title)
            known.update(classes)
    return out


def classes_by_item_name(game) -> Dict[str, set]:
    """{токен названия предмета в нижнем регистре: классы}

    Запись `Weapon_CowMangler` находит своё имя по токену локализации
    `TF_CowMangler`, но класса локализация не знает. Его знает предмет с тем
    же `item_name` в items_game
    """
    out: Dict[str, set] = {}
    for _key, block in game.items:
        token = (game.inherited(block, 'item_name') or '').lstrip('#').lower()
        if not token:
            continue
        classes = _item_classes(game, block)
        if classes:
            out.setdefault(token, set()).update(classes)
    return out
