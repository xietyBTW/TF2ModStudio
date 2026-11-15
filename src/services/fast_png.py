"""
Быстрый PNG для превью: сжатие полосами в несколько потоков

Pillow сжимает PNG одним потоком и перебирает фильтры строк: текстура 2048
стоит 150-220 мс, и уровень сжатия это почти не меняет. Здесь фильтр один
(Up, разность с верхней строкой, считается numpy), а поток deflate режется на
полосы, которые сжимаются одновременно: zlib отпускает GIL. Полосы стыкуются
полным сбросом (Z_FULL_FLUSH), так собирает поток и pigz

Файл выходит на четверть больше, чем у Pillow. Он временный и читается с
этой же машины
"""

from __future__ import annotations

import os
import struct
import zlib
from concurrent.futures import ThreadPoolExecutor

import numpy as np

_SIGNATURE = b"\x89PNG\r\n\x1a\n"
#: Заголовок потока zlib: deflate, окно 32 КБ, самый быстрый уровень
_ZLIB_HEADER = b"\x78\x01"
_FILTER_UP = 2
_LEVEL = 1
#: Меньше этого полосы не окупают раздачу по потокам
_MIN_STRIPE = 256 * 1024

_WORKERS = max(1, min(8, os.cpu_count() or 1))
_pool = ThreadPoolExecutor(max_workers=_WORKERS, thread_name_prefix="png")


def encode_rgba(rgba: bytes, width: int, height: int) -> bytes:
    """PNG из сырых RGBA-байтов (по 4 на пиксель, строками сверху вниз)"""
    if width <= 0 or height <= 0 or len(rgba) != width * height * 4:
        raise ValueError(f"RGBA size {len(rgba)} != {width}x{height}x4")
    rows = np.frombuffer(rgba, np.uint8).reshape(height, width * 4)
    raw = np.empty((height, width * 4 + 1), np.uint8)
    raw[:, 0] = _FILTER_UP
    raw[0, 1:] = rows[0]                 # над первой строкой - нули
    np.subtract(rows[1:], rows[:-1], out=raw[1:, 1:])
    data = memoryview(raw).cast("B")

    count = max(1, min(_WORKERS, len(data) // _MIN_STRIPE))
    step = -(-len(data) // count)
    stripes = [data[i:i + step] for i in range(0, len(data), step)]

    def squeeze(index: int) -> bytes:
        packer = zlib.compressobj(_LEVEL, zlib.DEFLATED, -zlib.MAX_WBITS)
        last = index == len(stripes) - 1
        return packer.compress(stripes[index]) + packer.flush(
            zlib.Z_FINISH if last else zlib.Z_FULL_FLUSH)

    packed = (list(_pool.map(squeeze, range(len(stripes)))) if len(stripes) > 1
              else [squeeze(0)])
    body = b"".join((_ZLIB_HEADER, *packed, struct.pack(">I", zlib.adler32(data))))
    header = struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)
    return b"".join((_SIGNATURE, _chunk(b"IHDR", header),
                     _chunk(b"IDAT", body), _chunk(b"IEND", b"")))


def _chunk(kind: bytes, data: bytes) -> bytes:
    return b"".join((struct.pack(">I", len(data)), kind, data,
                     struct.pack(">I", zlib.crc32(data, zlib.crc32(kind)))))
