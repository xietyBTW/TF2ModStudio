"""
План объединения модов: что в каждом и где они пересекаются

В одном VPK у файла может быть только одна версия. Два мода, которые кладут
файл по одному пути, - это конфликт, даже если моделей в них нет (две
перекраски одного обреза одними текстурами). Поэтому пересечение ищется по
путям файлов, а показывается по предметам: «c_scattergun - в двух модах»
понятнее списка VTF. Побеждает мод выше в списке - так же, как потом соберёт
merge_vpk_service
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Dict, List, Sequence

from src.shared.logging_config import get_logger

logger = get_logger(__name__)

#: Папки, которые ничего не говорят о предмете: подпись берётся глубже
_GENERIC = frozenset({'materials', 'models', 'weapons', 'c_models', 'w_models',
                      'player', 'items', 'workshop', 'workshop_partner', 'sound',
                      'particles', 'scripts', 'resource', 'vgui', 'console'})


def item_of(path: str) -> str:
    """Предмет, к которому относится файл мода, - для подписи в окне

    Модель и её спутники (.vvd, .dx90.vtx, .phy) - по имени модели; текстура
    - по своей папке (у оружия она названа как модель), если папка что-то
    значит; остальное - по имени файла
    """
    low = path.replace('\\', '/').lower()
    parts = low.split('/')
    name = parts[-1].split('.')[0]
    if low.startswith('models/'):
        return name
    if low.startswith('materials/'):
        if len(parts) > 2 and parts[1] == 'skybox':
            return 'skybox'
        folder = parts[-2] if len(parts) > 1 else ''
        return folder if folder and folder not in _GENERIC else name
    return name


def _files(vpk_path: Path) -> List[str]:
    import vpk

    try:
        return [p.replace('\\', '/').lower() for p in vpk.open(str(vpk_path))]
    except Exception as exc:                                  # noqa: BLE001
        logger.warning(f"не прочитан {vpk_path.name}: {exc}")
        return []


def describe(vpk_path: Path, limit: int = 6) -> Dict[str, object]:
    """Что в моде: {items: [предметы], more: сколько не вошло, files: число}"""
    files = _files(vpk_path)
    items = sorted({item_of(f) for f in files
                    if f.startswith(('models/', 'materials/')) and not f.endswith('.vmt')})
    return {'items': items[:limit], 'more': max(0, len(items) - limit),
            'files': len(files)}


def conflicts(vpk_paths: Sequence[Path]) -> List[Dict[str, object]]:
    """Пересечения выбранных модов, по предметам

    [{item, mods: [имена в порядке списка], winner, files: сколько общих}].
    Победитель - первый в списке: файлы остальных по тем же путям в сборку не
    попадут. `files` = 0 - одна модель лежит в модах по РАЗНЫМ путям
    (c_models и workshop_partner): в сборку войдут обе, но в игре видна будет
    одна, и какая - решает сама игра
    """
    owners: Dict[str, List[str]] = {}
    models: Dict[str, List[str]] = {}
    for vpk_path in vpk_paths:
        for f in set(_files(vpk_path)):
            owners.setdefault(f, []).append(vpk_path.name)
            if f.endswith('.mdl'):
                models.setdefault(item_of(f), []).append(vpk_path.name)
    by_item: Dict[str, Dict[str, object]] = {}
    for f, mods in owners.items():
        if len(mods) < 2:
            continue
        entry = by_item.setdefault(item_of(f), {'mods': [], 'files': 0})
        entry['files'] += 1
        for m in mods:
            if m not in entry['mods']:
                entry['mods'].append(m)
    for item, mods in models.items():
        if len(set(mods)) > 1 and item not in by_item:
            by_item[item] = {'mods': list(dict.fromkeys(mods)), 'files': 0}
    order = [p.name for p in vpk_paths]
    out = []
    for item, entry in sorted(by_item.items()):
        mods = sorted(entry['mods'], key=order.index)
        out.append({'item': item, 'mods': mods, 'winner': mods[0],
                    'files': entry['files']})
    return out


def size_of(vpk_path: Path) -> int:
    try:
        return os.path.getsize(vpk_path)
    except OSError:
        return 0
