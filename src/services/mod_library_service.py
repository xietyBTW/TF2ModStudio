"""
Библиотека чужих модов: папка на диске плюс правила обращения с ней

Зачем. Мод, открытый через браузер, приезжает во временную папку: путь к
исходному файлу страница не знает и знать не может. Временную папку рано или
поздно чистят, и «открой мод, который я смотрел вчера» превращается в «найди
его заново». Поэтому открытый мод кладётся в постоянную папку, и она же
работает списком

Отдельной базы нет намеренно: папка и есть список. Один источник правды,
никакой рассинхронизации индекса с файлами, и человек может положить туда
мод руками
"""

from __future__ import annotations

import json
import os
import shutil
from pathlib import Path
from typing import Dict, List, Optional

from src.shared.logging_config import get_logger
from src.shared.paths import data_dir

logger = get_logger(__name__)

#: Куда складываются открытые моды. Рядом с export - это тоже рабочие файлы
#: пользователя, а не служебный кэш
LIBRARY_DIR = data_dir() / 'mods'


def library_dir() -> Path:
    """Папка библиотеки, создаётся при первом обращении"""
    LIBRARY_DIR.mkdir(parents=True, exist_ok=True)
    return LIBRARY_DIR


def _free_name(name: str) -> Path:
    """
    Свободное имя в библиотеке

    Одноимённый мод не затираем: два разных `weapon.vpk` от разных авторов -
    обычное дело, и молча потерять один из них хуже, чем показать два
    """
    folder = library_dir()
    candidate = folder / name
    if not candidate.exists():
        return candidate
    stem, suffix = candidate.stem, candidate.suffix
    for i in range(1, 1000):
        candidate = folder / f"{stem}_{i}{suffix}"
        if not candidate.exists():
            return candidate
    raise RuntimeError('не подобрать имя в библиотеке модов')


def resolve(name: str) -> Optional[Path]:
    """
    Путь к моду по ИМЕНИ файла - или None, если такого в библиотеке нет

    Наружу отдаются только имена, и путь собирается здесь: иначе присланное
    «../../что-нибудь» увело бы открытие и удаление к любому файлу на диске
    """
    if not name:
        return None
    path = library_dir() / Path(str(name)).name
    return path if path.is_file() else None


def add(source: str) -> Optional[Path]:
    """
    Кладёт мод в библиотеку и отдаёт его новый путь

    Файл, который УЖЕ лежит в библиотеке, не копируется второй раз: иначе
    повторное открытие плодило бы `mod_1.vpk`, `mod_2.vpk` из одного и того же
    """
    if not source or not os.path.isfile(source):
        return None

    src = Path(source).resolve()
    folder = library_dir().resolve()
    if src.parent == folder:
        return src

    target = _free_name(src.name)
    shutil.copy2(src, target)
    logger.info(f"мод в библиотеке: {target}")
    # В том же виде, что и ветка выше: иначе повторное открытие того же мода
    # вернуло бы другой путь к нему
    return target.resolve()


def _icon_path(name: str, suffix: str = '.png') -> Path:
    folder = library_dir() / ICON_DIR_NAME
    folder.mkdir(parents=True, exist_ok=True)
    return folder / (Path(name).stem + suffix)


def _shot_path(name: str) -> Path:
    """Снимок модели из вьювера. Отдельно от обложки-текстуры: по нему видно,
    что мод уже сняли и снимать заново не нужно"""
    return _icon_path(name, SHOT_SUFFIX)


def _fresh(icon_file: Path, mod_mtime: float) -> bool:
    """Картинка есть и не старше мода: иначе она от прошлой версии файла"""
    try:
        return icon_file.stat().st_mtime >= mod_mtime
    except OSError:
        return False


def items() -> List[Dict[str, object]]:
    """Что лежит в библиотеке: имя, размер, когда добавлен. Новые сверху"""
    folder = library_dir()
    out: List[Dict[str, object]] = []
    for file in folder.glob('*.vpk'):
        try:
            stat = file.stat()
        except OSError:
            continue
        # Обложку здесь только ПОКАЗЫВАЕМ, если она уже есть: строить её на
        # каждый показ каталога - это декодировать VTF столько раз, сколько
        # модов в библиотеке. Недостающие достраиваются по одной (icon)
        shot = _shot_path(file.name)
        has_shot = _fresh(shot, stat.st_mtime)
        cover = shot if has_shot else _icon_path(file.name)
        out.append({
            'name': file.name,
            'path': str(file),
            'size': stat.st_size,
            'modified': stat.st_mtime,
            'icon': str(cover) if _fresh(cover, stat.st_mtime) else None,
            'shot': has_shot,
        })
    out.sort(key=lambda item: item['modified'], reverse=True)
    return out


def remove(name: str) -> bool:
    """Удаляет мод из библиотеки. False - такого файла в ней нет"""
    path = resolve(name)
    if path is None:
        return False
    try:
        path.unlink()
    except OSError as exc:
        logger.warning(f"не удалить мод {path}: {exc}")
        return False
    # Обложка без мода не нужна и опасна: одноимённый мод получил бы чужую
    for icon_file in (_icon_path(path.name), _shot_path(path.name),
                      _icon_path(path.name, TARGET_SUFFIX)):
        try:
            icon_file.unlink(missing_ok=True)
        except OSError:
            pass
    logger.info(f"мод удалён из библиотеки: {path}")
    return True


# Обложки
#
# Лучшая обложка - снимок модели, но снять её может только вьювер, и только
# когда мод открыли. До того обложкой служит основная текстура: она лежит в
# самом файле и достаётся чтением

#: Обложки живут рядом с модами, но отдельно: точка в имени прячет папку от
#: glob('*.vpk') и от глаз в проводнике
ICON_DIR_NAME = '.icons'
#: Номер - версия ракурса: поменяли, как снимаем, - поднимаем, и каждый мод
#: переснимется при следующем открытии
SHOT_SUFFIX = '.shot2.png'
#: Что заменяет мод: модель и её вид (оружие, косметика...)
TARGET_SUFFIX = '.target.json'
#: Крупнее не нужно: карточка в каталоге размером с ноготь
ICON_SIZE = 256


def read_target(name: str) -> Optional[Dict[str, str]]:
    """Что заменяет мод ({mdl, kind}), если уже узнавали. None - не узнавали
    или мод с тех пор поменялся. Узнать - открыть VPK, на каждый показ
    каталога это незачем"""
    mod = resolve(name)
    out = _icon_path(name, TARGET_SUFFIX)
    if mod is None or not _fresh(out, mod.stat().st_mtime):
        return None
    try:
        data = json.loads(out.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return None
    return {'mdl': str(data.get('mdl') or ''), 'kind': str(data.get('kind') or '')}


def write_target(name: str, mdl: str, kind: str) -> None:
    """Запоминает, что заменяет мод. Не записалось - узнаем в следующий раз"""
    try:
        _icon_path(name, TARGET_SUFFIX).write_text(
            json.dumps({'mdl': mdl, 'kind': kind}), encoding='utf-8')
    except OSError as exc:
        logger.warning(f"не запомнить цель мода {name}: {exc}")


def save_shot(name: str, png: bytes) -> Optional[Path]:
    """Кладёт снимок модели обложкой мода. None - мода нет или это не картинка"""
    from src.services.cover_shot import write_png

    mod = resolve(name)
    out = write_png(png, _shot_path(mod.name)) if mod else None
    if out is None:
        return None
    # Снимки прошлых версий ракурса больше никто не покажет
    for old in out.parent.glob(Path(mod.name).stem + '.shot*.png'):
        if old != out:
            old.unlink(missing_ok=True)
    return out


def _main_vtf(pak) -> Optional[bytes]:
    """
    Байты основной текстуры мода

    Порядок тот же, что у превью: сначала $baseTexture из VMT (авторитетно -
    так текстуру находит сама игра), и только потом догадка по именам файлов
    """
    from src.services.game_vpk_reader import GameVpkReader
    from src.services.preview_vpk_mod_worker import is_base_vtf

    paths = list(pak)
    for vmt in (p for p in paths if p.lower().endswith('.vmt')):
        try:
            content = pak[vmt].read().decode('utf-8', errors='ignore')
        except (KeyError, OSError):
            continue
        base = GameVpkReader.parse_basetexture(content)
        data = GameVpkReader.find_vtf_in_pak(pak, base) if base else None
        if data:
            return data

    # VMT может не быть вовсе (мод из одних текстур) - берём первую неслужебную
    for vtf in sorted(p for p in paths if p.lower().endswith('.vtf')):
        if is_base_vtf(vtf):
            try:
                return pak[vtf].read()
            except (KeyError, OSError):
                continue
    return None


def icon(name: str) -> Optional[Path]:
    """
    Путь к обложке мода, при необходимости строит её

    Обложка кэшируется на диске и переснимается, только если сам мод новее:
    декодировать VTF на каждый показ каталога незачем
    """
    mod = resolve(name)
    if mod is None:
        return None

    mtime = mod.stat().st_mtime
    shot = _shot_path(mod.name)
    if _fresh(shot, mtime):
        return shot
    out = _icon_path(mod.name)
    if _fresh(out, mtime):
        return out

    from PIL import Image
    from src.services.vpk_cache import open_vpk_cached
    from src.services.vtf_preview_service import vtf_bytes_to_png

    try:
        pak = open_vpk_cached(str(mod))
    except Exception as exc:                      # noqa: BLE001 - vpk кидает своё
        logger.warning(f"обложка: не открыть {mod.name}: {exc}")
        return None
    if pak is None:
        return None

    data = _main_vtf(pak)
    if not data or not vtf_bytes_to_png(data, str(out)):
        logger.info(f"обложка: в {mod.name} не нашлось основной текстуры")
        return None

    # Уменьшаем на месте: полноразмерная текстура в каталоге - мегабайты
    # трафика ради картинки в палец шириной
    try:
        with Image.open(out) as img:
            img.thumbnail((ICON_SIZE, ICON_SIZE))
            img.save(out)
    except OSError as exc:
        logger.warning(f"обложка: не уменьшить {out.name}: {exc}")
    return out
