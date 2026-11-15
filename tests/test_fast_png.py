"""
Быстрый PNG обязан читаться обратно пиксель в пиксель: поток deflate собран
из независимо сжатых полос, и ошибка на стыке дала бы битую текстуру в превью
"""

import io

import numpy as np
import pytest
from PIL import Image

from src.services import fast_png


def _noise(width, height, seed=1):
    return np.random.default_rng(seed).integers(
        0, 256, (height, width, 4), dtype=np.uint8).tobytes()


@pytest.mark.parametrize("size", [(1, 1), (3, 5), (64, 64), (512, 256), (1024, 1024)])
def test_roundtrip_matches_pixels(size):
    width, height = size
    rgba = _noise(width, height)
    with Image.open(io.BytesIO(fast_png.encode_rgba(rgba, width, height))) as img:
        img.load()
        assert img.mode == "RGBA" and img.size == size
        assert img.tobytes() == rgba


def test_large_image_is_packed_in_several_stripes(monkeypatch):
    # На одноядерной машине полоса одна: проверяем именно стыки
    monkeypatch.setattr(fast_png, "_WORKERS", 4)
    rgba = _noise(700, 700, seed=2)
    seen = []
    real = fast_png.zlib.compressobj

    def spy(*args, **kwargs):
        seen.append(1)
        return real(*args, **kwargs)

    monkeypatch.setattr(fast_png.zlib, "compressobj", spy)
    png = fast_png.encode_rgba(rgba, 700, 700)
    assert len(seen) > 1
    with Image.open(io.BytesIO(png)) as img:
        assert img.tobytes() == rgba


def test_flat_picture_compresses():
    rgba = bytes([10, 20, 30, 255]) * (512 * 512)
    assert len(fast_png.encode_rgba(rgba, 512, 512)) < len(rgba) // 50


def test_wrong_size_is_rejected():
    with pytest.raises(ValueError):
        fast_png.encode_rgba(b"\x00" * 15, 2, 2)
