"""
Где у прелоадера резервные копии файлов игры

Прелоадер (casual-preloader) переписывает частицы и небо прямо в архивах игры,
а их оригиналы держит у себя в `backup/`, разложенными по игровым путям
(`backup/particles/crit.pcf`). Путь к прелоадеру указывает человек (окно
первого запуска, настройки) - что ему привычнее: файл запуска (RUNME.bat,
ярлык) или папку. Копии отсюда сверяет с игрой game_integrity, поэтому лишняя
или чужая папка ничего не испортит

Раскладка прелоадера меняется от версии к версии, и путь к `backup/` не
запоминается: он находится заново при каждом запуске. Сначала - где он лежит
у нынешней версии, не нашлось - обход выбранной папки
"""

from __future__ import annotations

from pathlib import Path
from typing import List

from src.shared.logging_config import get_logger

logger = get_logger(__name__)

#: Где `backup/` у нынешней версии: рядом с RUNME.bat лежит casual-preloader/,
#: а у непереносной сборки копии в userdata/data
KNOWN = ('backup', 'casual-preloader/backup', 'userdata/data/backup',
         'casual-preloader/userdata/data/backup')
#: На сколько папок вверх от выбранного смотреть известные места: выбрать
#: могли и файл в глубине (core/main.py)
UP = 2
#: Обход выбранной папки - глубина и потолок папок: прелоадер небольшой, а
#: выбрать по ошибке могли и весь диск
WALK_DEPTH = 6
WALK_LIMIT = 20000


def find(chosen: str) -> List[Path]:
    """Папки с копиями файлов игры для выбранного файла или папки прелоадера"""
    if not chosen:
        return []
    start = Path(chosen)
    if start.is_file():
        start = start.parent
    if not start.is_dir():
        return []
    for base in [start, *list(start.parents)[:UP]]:
        found = [base / rel for rel in KNOWN if looks_like_copy(base / rel)]
        if found:
            return _outermost(found)
    found = _walk(start)
    if found:
        logger.info(f"[прелоадер] копии нашлись обходом: {[str(p) for p in found]}")
    return found


def looks_like_copy(folder: Path) -> bool:
    """Папка похожа на копию файлов игры: игровые папки с файлами внутри"""
    try:
        if (folder / 'particles').is_dir() and any((folder / 'particles').glob('*.pcf')):
            return True
        return (folder / 'materials').is_dir() and any((folder / 'materials').iterdir())
    except OSError:
        return False


def count_files(folders: List[Path]) -> int:
    """Сколько разных файлов игры в копиях - человеку, чтобы видел, что
    нашлось. Копий у прелоадера бывает две одинаковых, считаем по пути"""
    return len({p.relative_to(f).as_posix().lower()
                for f in folders for p in f.rglob('*') if p.is_file()})


def _walk(start: Path) -> List[Path]:
    """Обход папки вширь: копии, как бы ни назвала их новая версия"""
    found: List[Path] = []
    level, seen = [start], 0
    for _ in range(WALK_DEPTH):
        nxt: List[Path] = []
        for folder in level:
            seen += 1
            if seen > WALK_LIMIT:
                return _outermost(found)
            if looks_like_copy(folder):
                found.append(folder)
                continue                    # внутрь копии не идём
            try:
                nxt.extend(c for c in folder.iterdir() if c.is_dir())
            except OSError:
                continue
        level = nxt
    return _outermost(found)


def _outermost(folders: List[Path]) -> List[Path]:
    """Без вложенных друг в друга и без повторов"""
    out: List[Path] = []
    for folder in sorted(set(folders), key=lambda p: len(p.parts)):
        if not any(parent in out for parent in folder.parents):
            out.append(folder)
    return out
