"""
Файлы игры, переписанные чужой программой (прелоадер и подобные)

Прелоадер (casual-preloader) ставит моды в казуал, переписывая файлы прямо
внутри игровых архивов `tf2_misc_0xx.vpk`. Каталог `*_dir.vpk` он не трогает,
и CRC32 каждого файла там остаётся от оригинала. Поэтому подмена видна точно,
по самим данным, без списков модов и догадок по датам. Без этого приложение
принимало мод за игру: в превью - чужая модель, в редакторе частиц - чужой
эффект вместо стокового, а разбор модели оседал в кэше

Что делаем с подменённым файлом:
- ищем оригинал среди резервных копий. У прелоадера они в его папке
  `backup/`, разложены по игровым путям. Копию берём, только если её CRC
  совпал с каталогом игры: чужой копии на слово не верим, и годится любой
  источник;
- оригинала нет - отдаём что есть, но запоминаем: страница скажет человеку, а
  кэш разборов моделей такое не сохраняет (`is_modified`), иначе подмена
  пережила бы проверку файлов игры в Steam
"""

from __future__ import annotations

import os
import re
import threading
import zlib
from contextlib import contextmanager
from pathlib import Path
from typing import Callable, Dict, List, Optional

from src.shared.logging_config import get_logger

logger = get_logger(__name__)

#: Каталоги архивов самой игры. Моды так не называют, а у модов CRC бывает
#: неверным по вине собравшей их программы - это не подмена игры
_GAME_VPK = re.compile(r'^(tf2|hl2)_[a-z0-9_]+_dir\.vpk$', re.IGNORECASE)

_lock = threading.Lock()
#: {игровой путь: взят ли проверенный оригинал}
_modified: Dict[str, bool] = {}
_listeners: List[Callable[[], None]] = []
_sources: Optional[List[Path]] = None


def is_game_vpk(dir_vpk_path: str) -> bool:
    """Архив самой игры, а не мод"""
    return bool(_GAME_VPK.match(os.path.basename(str(dir_vpk_path or ''))))


def checked(data: bytes, rel: str, crc: int) -> bytes:
    """Данные файла игры: как есть, если CRC сошёлся, иначе проверенный
    оригинал, а без него - что есть (подмена запоминается). В `as_installed`
    подменённый отдаётся как есть: человек сам выбрал править установленный"""
    if zlib.crc32(data) & 0xFFFFFFFF == crc:
        return data
    original = _original(rel, crc)
    _remember(rel, original is not None)
    if getattr(_reading, 'installed', False):
        return data
    return original if original is not None else data


#: Режим чтения потока: «как установлено» (as_installed)
_reading = threading.local()


@contextmanager
def as_installed():
    """Читать файлы игры так, как они сейчас лежат, - с модом, который
    прелоадер вписал в игру. Выбирает человек (редактор частиц): чтобы
    доработать установленный мод, а не начинать со стока"""
    was = getattr(_reading, 'installed', False)
    _reading.installed = True
    try:
        yield
    finally:
        _reading.installed = was


def is_patched(rel: str) -> bool:
    """Файл игры переписан чужой программой (уже читали и видели)"""
    with _lock:
        return _norm(rel) in _modified


def is_modified(prefix: str) -> bool:
    """Есть ли среди прочитанных файлов под `prefix` подменённые без
    оригинала. Префикс - путь без расширения: у модели их несколько файлов"""
    want = _norm(prefix)
    with _lock:
        return any(not restored and path.startswith(want)
                   for path, restored in _modified.items())


def summary() -> Dict[str, object]:
    """Для страницы: сколько подменённых, сколько из них заменено оригиналом"""
    with _lock:
        modified = sorted(p for p, restored in _modified.items() if not restored)
        restored = sorted(p for p, restored in _modified.items() if restored)
    return {'modified': modified, 'restored': restored}


def on_change(listener: Callable[[], None]) -> None:
    """Слушатель новых подмен. Зовётся из потока, который читал файл"""
    with _lock:
        _listeners.append(listener)


def reset() -> None:
    """Забывает найденное и папки с копиями (для тестов и после смены игры)"""
    global _sources
    with _lock:
        _modified.clear()
        _sources = None


def forget_sources() -> None:
    """Путь к прелоадеру сменили: копии ищутся заново, а подмены без
    оригинала - проверяются снова (оригинал мог найтись)"""
    global _sources
    with _lock:
        _sources = None
        for path in [p for p, restored in _modified.items() if not restored]:
            del _modified[path]


def _remember(rel: str, restored: bool) -> None:
    path = _norm(rel)
    with _lock:
        known = _modified.get(path)
        _modified[path] = restored or bool(known)
        listeners = list(_listeners) if known is None else []
    if known is not None:
        return                                  # уже сказано
    if restored:
        logger.info(f"[целостность] {path} изменён в игре - взят оригинал из копии")
    else:
        logger.warning(f"[целостность] {path} изменён в игре чужой программой, "
                       f"оригинала нет")
    for listener in listeners:
        try:
            listener()
        except Exception as exc:                              # noqa: BLE001
            logger.debug(f"[целостность] слушатель упал: {exc}")


def _original(rel: str, crc: int) -> Optional[bytes]:
    """Проверенный оригинал из резервных копий или None"""
    parts = _norm(rel).split('/')
    for root in sources():
        candidate = root.joinpath(*parts)
        try:
            data = candidate.read_bytes()
        except OSError:
            continue
        if zlib.crc32(data) & 0xFFFFFFFF == crc:
            return data
    return None


def sources() -> List[Path]:
    """Папки с резервными копиями файлов игры - у прелоадера, путь к которому
    указал человек (по дискам приложение не ходит). Ищутся раз за сеанс"""
    global _sources
    with _lock:
        if _sources is not None:
            return list(_sources)
    from src.config.app_config import AppConfig
    from src.services import preloader_backups

    found = preloader_backups.find(str(AppConfig.load_config().get('preloader_path') or ''))
    with _lock:
        _sources = found
    if found:
        logger.info(f"[целостность] резервные копии игры: {[str(p) for p in found]}")
    return list(found)


def _norm(path: str) -> str:
    return str(path or '').replace('\\', '/').strip('/').lower()


class CheckedFile:
    """Файл игрового архива, чьё полное чтение сверяется с CRC каталога.
    Частичное чтение (заголовки) идёт как есть: сверять там нечего"""

    def __init__(self, inner, rel: str):
        self._inner = inner
        self._rel = rel

    def read(self, size: int = -1) -> bytes:
        if (size is None or size < 0) and self._inner.tell() == 0:
            return checked(self._inner.read(), self._rel, self._inner.crc32)
        return self._inner.read(size)

    def save(self, path) -> None:
        self._inner.seek(0)
        Path(path).write_bytes(self.read())

    def __getattr__(self, name):
        return getattr(self._inner, name)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self._inner.close()


def guard(pak, dir_vpk_path: str):
    """Подключает сверку к открытому архиву игры. Архивы модов не трогает"""
    plain = getattr(pak, 'get_vpkfile_instance', None)
    if plain is None or not is_game_vpk(dir_vpk_path):
        return pak

    def checked_instance(path, metadata):
        return CheckedFile(plain(path, metadata), path)

    pak.get_vpkfile_instance = checked_instance
    return pak
