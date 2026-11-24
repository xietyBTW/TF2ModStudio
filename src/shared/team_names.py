"""Командные имена материалов и текстур: чья синяя пара и где основа

Единственная копия правила. Синий суффикс бывает `_blue` и `_blu`, стоит в
конце (`c_scattergun_blue`) или перед вариантным (`c_ambassador_opt_blue_xmas`),
а основа может уже нести `_red` (`festive_lights_red` / `festive_lights_blue`)"""

from typing import Dict, Tuple

#: Вариантные суффиксы: суффикс -> вид варианта. '_strange'/'_unusual'
#: встречаются редко (обычно padding-строки не переименованы), но
#: исключаются из базовых на всякий случай
VARIANT_SUFFIXES: Dict[str, str] = {
    '_australium': 'australium',
    '_gold':       'australium',
    '_festive':    'festive',
    '_xmas':       'festive',
    '_botkiller':  'botkiller',
    '_strange':    'strange',
    '_unusual':    'unusual',
}

BLUE_SUFFIXES = ('_blue', '_blu')


def team_form(name: str) -> Tuple[str, bool]:
    """(основа в нижнем регистре, синий?) - имя без командного суффикса"""
    low = (name or '').lower()
    tail = next((s for s in VARIANT_SUFFIXES if low.endswith(s)), '')
    low = low[:len(low) - len(tail)]
    for suffix in BLUE_SUFFIXES:
        if low.endswith(suffix):
            return low[:-len(suffix)] + tail, True
    if low.endswith('_red'):
        low = low[:-4]
    return low + tail, False


def is_red(name: str) -> bool:
    """Явно красное имя: `_red` в конце или перед вариантным суффиксом"""
    low = (name or '').lower()
    tail = next((s for s in VARIANT_SUFFIXES if low.endswith(s)), '')
    return low[:len(low) - len(tail)].endswith('_red')


def is_blue(name: str) -> bool:
    """Синее ли имя по суффиксу"""
    return team_form(name)[1]


def is_blue_of(red: str, blue: str) -> bool:
    """Синяя ли `blue` пара красной `red`"""
    red_base, red_blue = team_form(red)
    blue_base, blue_blue = team_form(blue)
    return blue_blue and not red_blue and red_base == blue_base


def blue_name(red: str) -> str:
    """Имя новой синей пары: `x_red` -> `x_blue`, иначе `x` -> `x_blue`"""
    return (red[:-4] if red.lower().endswith('_red') else red) + '_blue'
