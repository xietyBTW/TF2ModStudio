"""Перекраска текстуры под австралий этого же оружия

Цвет и блеск берутся из игрового золота предмета, а не из одной общей
краски: у каждого австралия своё золото. Яркость своей картинки
раскладывается по процентилям и получает цвет тех же процентилей игрового
золота - тёмное становится тёмным золотом, светлое светлым, рисунок цел.
Альфа тоже из золота: у его VMT `$basemapalphaphongmask`, и в ней блеск
"""

from __future__ import annotations

import numpy as np
from PIL import Image

#: Сколько ступеней палитры. Больше незачем: глаз разницы не видит
_STEPS = 256


def _luma(rgba: np.ndarray) -> np.ndarray:
    return rgba[..., 0] * 0.299 + rgba[..., 1] * 0.587 + rgba[..., 2] * 0.114


def gold_palette(gold_png: str) -> np.ndarray:
    """Палитра (256, 4) золота: средний цвет каждой ступени яркости"""
    with Image.open(gold_png) as img:
        px = np.asarray(img.convert('RGBA'), np.float32).reshape(-1, 4)
    px = px[np.argsort(_luma(px), kind='stable')]
    chunks = np.array_split(px, _STEPS)
    return np.stack([c.mean(axis=0) if len(c) else px.mean(axis=0) for c in chunks])


def recolor(base_png: str, gold_png: str, out_png: str) -> str:
    """Своя картинка в золото этого оружия -> out_png"""
    palette = gold_palette(gold_png)
    with Image.open(base_png) as img:
        base = np.asarray(img.convert('RGBA'), np.float32)
    shape = base.shape[:2]
    luma = _luma(base.reshape(-1, 4))
    # Процентиль яркости каждого пикселя. Одинаковая яркость - одна ступень:
    # иначе ровная заливка рассыпалась бы в золотой шум
    ordered = np.sort(luma)
    middle = (np.searchsorted(ordered, luma, 'left')
              + np.searchsorted(ordered, luma, 'right') - 1) / 2
    step = np.rint(middle * (_STEPS - 1) / max(1, len(luma) - 1)).astype(np.int64)
    out = palette[step].reshape(*shape, 4)
    Image.fromarray(np.clip(out + 0.5, 0, 255).astype(np.uint8), 'RGBA').save(out_png)
    return out_png
