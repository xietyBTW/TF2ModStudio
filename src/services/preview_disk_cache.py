"""
Запас превью на диске: готовые OBJ моделей и PNG текстур

Запас в памяти (smd_to_obj_service, vtf_preview_service) мал и живёт до
закрытия приложения. Здесь то же самое лежит файлами: предмет, который уже
открывали, показывается без разбора SMD и без сжатия PNG, в том числе после
перезапуска

Ключ - отпечаток входа (у текстуры содержимое VTF, у модели файлы SMD со
временем правки и поза), поэтому устаревшая запись просто не находится и
уходит по давности. Запись - один файл, пишется заменой: читатель не застанет
половину
"""

from __future__ import annotations

import os
import shutil
import threading
import uuid
from pathlib import Path
from typing import Optional

from src.shared.logging_config import get_logger
from src.shared.paths import data_dir

logger = get_logger(__name__)

#: Папка запаса. None - запас выключен (тесты)
DIR: Optional[Path] = data_dir() / "cache" / "preview"

#: Смена числа бросает прежние записи: OBJ или PNG стали собираться иначе
VERSION = 1

#: Потолок размера. Текстура 2048 - около 3 МБ, модель - 2-3 МБ
MAX_MB = 512
#: После уборки остаётся эта доля потолка, чтобы не убирать на каждой записи
_KEEP_SHARE = 0.8
#: Уборка идёт фоном, когда с прошлой записано столько байт
_SWEEP_EVERY = 32 * 1024 * 1024

_lock = threading.Lock()
_trim_lock = threading.Lock()
_written = 0


def _path(kind: str, key: bytes) -> Optional[Path]:
    return DIR / f"v{VERSION}" / kind / key.hex() if DIR is not None else None


def get(kind: str, key: bytes) -> Optional[bytes]:
    """Запись целиком или None"""
    path = _path(kind, key)
    if path is None:
        return None
    try:
        data = path.read_bytes()
    except OSError:
        return None
    try:
        os.utime(path)                  # давность считается от последнего чтения
    except OSError:
        pass
    return data


def put(kind: str, key: bytes, data: bytes) -> None:
    """Кладёт запись. Диск не дал - превью обойдётся без запаса"""
    path = _path(kind, key)
    if path is None:
        return
    tmp = path.with_name(f"{path.name}.{uuid.uuid4().hex[:8]}.tmp")
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp.write_bytes(data)
        os.replace(tmp, path)
    except OSError as exc:
        logger.debug(f"[preview-cache] запись не легла: {exc}")
        try:
            tmp.unlink()
        except OSError:
            pass
        return
    _count_written(len(data))


def drop(kind: str, key: bytes) -> None:
    """Убирает запись, которая не прочиталась"""
    path = _path(kind, key)
    if path is not None:
        try:
            path.unlink()
        except OSError:
            pass


def _count_written(size: int) -> None:
    global _written
    with _lock:
        _written += size
        due = _written >= _SWEEP_EVERY
        if due:
            _written = 0
    if due:
        threading.Thread(target=trim, name="preview-cache-trim", daemon=True).start()


def _files() -> list:
    """[(время, размер, путь)] всех файлов запаса, включая прежние версии"""
    found = []
    if DIR is None or not DIR.is_dir():
        return found
    for path in DIR.rglob("*"):
        try:
            st = path.stat()
        except OSError:
            continue
        if path.is_file():
            found.append((st.st_mtime, st.st_size, path))
    return found


def trim(max_mb: float = MAX_MB) -> int:
    """
    Удаляет самые давние записи, пока запас не уложится в потолок

    Returns:
        сколько файлов удалено
    """
    with _trim_lock:
        files = _files()
        total = sum(size for _t, size, _p in files)
        limit = max_mb * 1024 * 1024
        if total <= limit:
            return 0
        removed = 0
        for _mtime, size, path in sorted(files, key=lambda f: f[0]):
            if total <= limit * _KEEP_SHARE:
                break
            try:
                path.unlink()
            except OSError:
                continue
            total -= size
            removed += 1
        logger.info(f"[preview-cache] убрано давних записей: {removed}")
        return removed


def size_mb() -> float:
    return sum(size for _t, size, _p in _files()) / (1024 * 1024)


def clear() -> int:
    """Удаляет весь запас. Returns: сколько файлов было"""
    count = len(_files())
    if DIR is not None:
        shutil.rmtree(DIR, ignore_errors=True)
    return count
