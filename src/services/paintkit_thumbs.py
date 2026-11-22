"""
Миниатюры War Paint для списка раскрасок и недавно нанесённые

Миниатюра - рецепт без износа на развёртке пушки, под которую его отдаёт
каталог (donor): так видно и цвета, и узор, а не одну плитку слоя. Собирается
раз и лежит на диске, список просит только видимые строки
"""

from __future__ import annotations

import os
import threading
from typing import List

import numpy as np

#: Сколько последних нанесённых раскрасок держать сверху списка
RECENT = 5
RECENT_KEY = 'warpaint_recent'


def thumb(defs, kit_id: int, item_id: int, loader, out_dir: str, size: int = 64) -> str:
    """PNG миниатюры (путь) или '' - рецепта у этой пары нет"""
    from PIL import Image

    from src.data.paintkit_defs import find_item
    from src.services.paintkit_compositor import PaintkitCompositor

    out = os.path.join(out_dir, f'{int(kit_id)}_{int(item_id)}_{int(size)}.png')
    if os.path.isfile(out):
        return out
    kit, item = find_item(defs, kit_id, item_id)
    recipe = defs.recipe(kit, item, 1, strip_stickers=True) if kit and item else None
    if recipe is None:
        return ''
    rgb = np.ascontiguousarray(PaintkitCompositor(loader, size, 'red').compose(recipe, seed=0)[..., :3])
    os.makedirs(out_dir, exist_ok=True)
    # Через временный файл: две строки могут попросить одну миниатюру разом
    tmp = f'{out}.{os.getpid()}.{threading.get_ident()}.tmp'
    Image.fromarray(rgb, 'RGB').save(tmp, format='PNG')
    os.replace(tmp, out)
    return out


def recent(raw) -> List[int]:
    """Недавние из конфига без мусора: там мог оказаться что угодно"""
    return [k for k in (raw if isinstance(raw, list) else [])
            if isinstance(k, int) and not isinstance(k, bool)][:RECENT]


def remember(raw, kit_id: int) -> List[int]:
    """Недавние с ``kit_id`` первым, без повторов"""
    return [int(kit_id), *(k for k in recent(raw) if k != int(kit_id))][:RECENT]
