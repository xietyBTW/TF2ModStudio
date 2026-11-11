"""
Текстуры сцены (от первого лица, на персонаже, насмешка) из архивов

У каждой части сцены свой `$cdmaterials`: оружие, руки, персонаж, шапка. Имя
ищется по папкам частей по очереди, найденное второй раз не ищется. Цикл был
скопирован в три воркера, и VPK мода знал только один из них: на персонаже
мод оставался с игровой текстурой
"""

from __future__ import annotations

from typing import Dict, Iterable, List, Sequence, Tuple


def archives(mod_vpk: str, textures_vpk: str, misc_vpk: str) -> List[str]:
    """Где искать файлы сцены. Мод - первым: так его видит игра"""
    return [p for p in (mod_vpk, textures_vpk, misc_vpk) if p]


def resolve(resolver, groups: Iterable[Tuple[Sequence[str], Sequence[str]]]
            ) -> Tuple[Dict[str, str], Dict[str, dict]]:
    """({материал: png}, {материал: свойства}) по группам (имена, $cdmaterials)

    `resolver` - MaterialResolver сцены
    """
    textures: Dict[str, str] = {}
    hints: Dict[str, dict] = {}
    for names, cdmaterials in groups:
        left = [n for n in names if n not in textures]
        if not left:
            continue
        textures.update({n: png for n, png
                         in resolver.texture_map(left, list(cdmaterials)).items() if png})
        hints.update(resolver.render_map(left, list(cdmaterials)))
    return textures, hints
