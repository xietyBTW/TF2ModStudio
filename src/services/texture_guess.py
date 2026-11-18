"""
Догадки, где лежит текстура материала, когда его VMT в игре не нашёлся

Игра ищет текстуру только через VMT -> $basetexture (MaterialResolver.find_vtf),
и догадки нужны лишь там, где VMT нет: предмет без QC, имя материала без
папки. Список один на превью и сборку: раньше у каждой был свой, и они
находили разные файлы

Пути - в виде значения $baseTexture: от materials/, без расширения
"""

from typing import List, Optional

#: Командный суффикс головы персонажа: VTF один, тонируется в VMT
TEAM_SUFFIXES = ("_red", "_blue")
#: Оверлей-меши рук (киллстрик): своего VTF нет, рисуются базовым
OVERLAY_SUFFIXES = ("_sheen2", "_sheen", "_overlay", "_fresnel")

#: Папки оружия по порядку: c_items раньше мастерской (старые модели)
_WEAPON_DIRS = (
    "models/workshop_partner/weapons/c_models/{n}/{n}",
    "models/weapons/c_models/{n}/{n}",
    "models/weapons/c_items/{n}",
    "models/workshop/weapons/c_models/{n}/{n}",
)


def weapon_paths(name: str) -> List[str]:
    """Стандартные места текстуры оружия по его имени"""
    n = (name or "").lower()
    return [d.format(n=n) for d in _WEAPON_DIRS] if n else []


def player_paths(folder: Optional[str], name: str) -> List[str]:
    """Папка персонажа: имя как есть, затем без командного или оверлейного
    суффикса (scout_head_red -> scout_head, hvyweapon_hands_sheen ->
    hvyweapon_hands)"""
    if not folder:
        return []
    n = (name or "").lower()
    paths = [f"models/player/{folder}/{n}"]
    for suffixes in (TEAM_SUFFIXES, OVERLAY_SUFFIXES):
        for suf in suffixes:
            if n.endswith(suf):
                paths.append(f"models/player/{folder}/{n[:-len(suf)]}")
                break
    return paths
