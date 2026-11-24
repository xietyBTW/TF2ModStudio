"""
Предметы, которые берут у общей модели не нулевую строку скина

«Критокола» - та же модель, что «Бонк! Атомный залп» (`c_energy_drink`), но
с `"visuals" { "skin" "2" }`: фиолетовая банка - строка 2 её таблицы
скинов. В QC об этом ничего нет, там строка просто «Skin 2», а такие
безымянные строки в полосу стилей не попадают (у тел персонажей это
служебные скины). Имя строке даёт только items_game - он здесь и читается

Публичное API:
  item_skin_styles(tf2_root) -> {стебель модели: {строка скина: токен имени}}
  styled_skins(weapon_key, tf2_root, lang) -> [(имя, строка скина), ...]
"""

import os
import re
from functools import lru_cache
from typing import Dict, List, Tuple

from src.data.weapon_model_index import get_items_game_path

_SLOTS = frozenset({"primary", "secondary", "melee", "pda", "pda2", "building"})
_MODEL_RE = re.compile(r'"model_player"\s+"([^"]+\.mdl)"', re.I)
_SKIN_RE = re.compile(r'"skin"\s+"(\d+)"')
_BLOCK_RE = re.compile(r'"([^"]+)"\s*\{')


def item_skin_styles(tf2_root: str) -> Dict[str, Dict[int, str]]:
    """{стебель модели: {строка скина: токен имени предмета}}; первым
    выигрывает меньший индекс предмета (обычный раньше редких вариантов)"""
    path = get_items_game_path(tf2_root)
    if path is None:
        return {}
    st = os.stat(path)
    return _parse(str(path), st.st_mtime_ns, st.st_size)


@lru_cache(maxsize=2)
def _parse(path: str, _mtime_ns: int, _size: int) -> Dict[str, Dict[int, str]]:
    from src.data.items_game_kv import ItemsGame, flat_value

    game = ItemsGame.load(path)
    out: Dict[str, Dict[int, str]] = {}
    if game is None:
        return out
    for _idx, block in game.items:
        if (game.inherited(block, "item_slot") or "").lower() not in _SLOTS:
            continue
        model = game.inherited_match(block, _MODEL_RE)
        if not model:
            continue
        stem = os.path.splitext(os.path.basename(model.replace("\\", "/")))[0].lower()
        # Имя у части предметов приходит из prefab (Перчатки беглеца)
        token = (game.inherited(block, "item_name") or flat_value(block, "name") or "").lstrip("#")
        visuals = game.inherited_block(block, "visuals") or ""
        # Свой предмет на той же модели: `visuals { skin }` у Критоколы,
        # `visuals_red { skin }` у Перчаток беглеца (BLU - соседняя строка)
        for text in (_own_skin_block(visuals), game.inherited_block(block, "visuals_red") or ""):
            skin = _SKIN_RE.search(text)
            if skin and skin.group(1) != "0":
                out.setdefault(stem, {}).setdefault(int(skin.group(1)), token)
        # Стиль предмета: `styles { N { skin_red, name } }` - «Чёрный» у Чёрной розы
        for skin, name in _style_skins(visuals):
            out.setdefault(stem, {}).setdefault(skin, name)
    return out


def _blocks(text: str, start: int = 0):
    """(имя, тело) вложенных блоков `"имя" { … }` на одном уровне - по скобкам"""
    pos = start
    while True:
        head = _BLOCK_RE.search(text, pos)
        if not head:
            return
        depth, i = 1, head.end()
        while i < len(text) and depth:
            depth += {'{': 1, '}': -1}.get(text[i], 0)
            i += 1
        yield head.group(1), text[head.end():i - 1]
        pos = i


def _own_skin_block(visuals: str) -> str:
    """`visuals` без вложенных блоков: `skin` стиля не должен сойти за свой.
    Блок приходит вместе с внешними скобками - их снимаем"""
    text = visuals.strip()
    if text.startswith('{') and text.endswith('}'):
        text = text[1:-1]
    out, depth = [], 0
    for ch in text:
        depth += {'{': 1, '}': -1}.get(ch, 0)
        if depth == 0 and ch not in '{}':
            out.append(ch)
    return ''.join(out)


def _style_skins(visuals: str) -> List[Tuple[int, str]]:
    """[(строка скина, токен имени)] именованных стилей с ненулевым скином"""
    found: List[Tuple[int, str]] = []
    for name, body in _blocks(visuals):
        if name.lower() != "styles":
            continue
        for _n, style in _blocks(body):
            skin = re.search(r'"skin_red"\s+"(\d+)"', style)
            title = re.search(r'"name"\s+"([^"]+)"', style)
            if skin and title and skin.group(1) != "0":
                found.append((int(skin.group(1)), title.group(1).lstrip("#")))
    return found


def styled_skins(weapon_key: str, tf2_root: str, lang: str = "en") -> List[Tuple[str, int]]:
    """Строки скина этой модели, у которых есть свой предмет: [(имя, строка)]"""
    from src.data.hats_parser import parse_localization

    rows = item_skin_styles(tf2_root).get((weapon_key or "").lower())
    if not rows:
        return []
    loc = parse_localization(tf2_root, "russian" if lang == "ru" else "english")
    return [(loc.get(token) or loc.get(token.lower()) or token, skin)
            for skin, token in sorted(rows.items())]
