"""
«Не красить»: детали, на которые War Paint не ложится

В раскладке War Paint (paintkit_layout) у такой детали слой KEEP. Рецепт его
не знает - и не должен: рецепт Valve подписан, а слой вне его набора рецепт и
так отдаёт автомату. Поэтому War Paint собирается как обычно, а потом по
развёртке этих деталей поверх него возвращается то, что лежало на карточке
до War Paint (своя картинка человека или игровая)
"""

from __future__ import annotations

import hashlib
import os
from typing import Dict, List, Optional, Set, Tuple

import numpy as np

from src.shared.logging_config import get_logger

logger = get_logger(__name__)

#: Слой «Не красить» в раскладке человека
KEEP = -1
#: Запас маски в пикселях на 1024: у края детали иначе остаётся полоска
#: War Paint - текстуру фильтруют и уменьшают мипмапами
_BLEED_1024 = 3


def split(assign: Optional[Dict[str, int]]) -> Tuple[Optional[Dict[str, int]], Set[str]]:
    """(раскладка для рецепта без «Не красить», ключи деталей «Не красить»)"""
    kept = {k for k, v in (assign or {}).items() if int(v) == KEEP}
    rest = {k: v for k, v in (assign or {}).items() if int(v) != KEEP}
    return rest or None, kept


def polygons(units, kept: Set[str]) -> List:
    """UV-треугольники деталей «Не красить» (Unit.uv из paintkit_generic)"""
    return [tri for u in units if u.key in kept for tri in u.uv]


def mask(polys: List, size: Tuple[int, int]) -> np.ndarray:
    """Маска 0/255 по развёртке, тем же растром, что раскладывает узоры, с
    запасом по краю"""
    from PIL import Image, ImageFilter

    from src.services.paintkit_generic import _rasterize

    w, h = size
    side = max(w, h)
    raw = _rasterize([(255, polys)], side)
    img = Image.fromarray(raw, 'L')
    bleed = max(1, round(_BLEED_1024 * side / 1024))
    img = img.filter(ImageFilter.MaxFilter(bleed * 2 + 1))
    if img.size != (w, h):
        img = img.resize((w, h), Image.NEAREST)
    return np.asarray(img)


def apply(painted: str, under: str, polys: List, out_dir: str) -> str:
    """
    War Paint ``painted`` с прежней текстурой ``under`` на деталях ``polys``.
    Новый файл - имя по содержимому всего, от чего зависит картинка; без
    деталей или без прежней текстуры - ``painted`` как есть
    """
    if not polys or not under or not os.path.isfile(under):
        return painted
    from PIL import Image

    stamp = hashlib.sha1(repr((painted, os.path.getmtime(painted), under,
                               os.path.getmtime(under), len(polys),
                               polys[0], polys[-1])).encode('utf-8')).hexdigest()[:12]
    out = os.path.join(out_dir, f'{os.path.splitext(os.path.basename(painted))[0]}_keep_{stamp}.png')
    if os.path.isfile(out):
        return out
    try:
        with Image.open(painted) as p:
            top = p.convert('RGBA')
        with Image.open(under) as u:
            base = u.convert('RGBA')
        if base.size != top.size:
            base = base.resize(top.size, Image.LANCZOS)
        keep = Image.fromarray(mask(polys, top.size), 'L')
        Image.composite(base, top, keep).save(out, compress_level=1)
        return out
    except OSError as exc:
        logger.warning(f'[paintkit] «Не красить» не легло: {exc}')
        return painted
