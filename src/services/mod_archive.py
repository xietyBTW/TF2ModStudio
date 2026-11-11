"""
Мод не в виде VPK: ZIP-архив или папка - в VPK библиотеки модов

С GameBanana моды приходят архивами: внутри готовый VPK (иногда несколько, или
многотомный `_dir.vpk` с `_000.vpk`), либо распакованная папка мода, как её
кладут в `tf/custom` (materials, models, sound...). Всё это превращается в
обычные VPK-файлы библиотеки - дальше мод открывается и собирается тем же
путём, что и VPK

Архив чужой, поэтому распаковка недоверчивая: пути внутри не выходят за свою
папку, а размер, число файлов и сжатие ограничены - архивная бомба на сотни
гигабайт иначе заняла бы диск целиком
"""

from __future__ import annotations

import os
import re
import shutil
import tempfile
import zipfile
from pathlib import Path
from typing import List

from src.shared.logging_config import get_logger

logger = get_logger(__name__)

#: Папки верхнего уровня мода в tf/custom: по ним видно, где корень мода
MOD_DIRS = frozenset({'materials', 'models', 'sound', 'particles', 'scripts',
                      'resource', 'maps', 'cfg', 'media'})
#: Пределы распаковки: модам TF2 этого с запасом хватает
MAX_FILES = 50_000
MAX_TOTAL = 4 * 1024 ** 3
MAX_RATIO = 200
#: Том многотомного VPK (`имя_000.vpk`): открывается через его `_dir.vpk`
_CHUNK = re.compile(r'_\d{3}\.vpk$', re.IGNORECASE)


class ModArchiveError(Exception):
    """Не мод или не распаковать: текст - для человека"""


def import_mod(source: str, language: str = 'ru') -> List[Path]:
    """VPK библиотеки из ZIP, папки или многотомного VPK

    Returns:
        пути новых VPK в библиотеке, по одному на найденный мод

    Raises:
        ModArchiveError: внутри нет ни VPK, ни папки мода, или архив опасен
    """
    path = Path(source)
    with tempfile.TemporaryDirectory(prefix='tf2sg_modimport_') as tmp:
        work = Path(tmp)
        if path.is_dir():
            root, name = path, path.name
        elif path.suffix.lower() == '.zip':
            root, name = work / 'zip', path.stem
            extract_zip(path, root)
        elif path.suffix.lower() == '.vpk':
            root, name = path.parent, path.stem
        else:
            raise ModArchiveError('Нужен VPK, ZIP или папка мода')

        unpacked = path.is_dir() or path.suffix.lower() == '.zip'
        made = [_to_library(v, work, language)
                for v in (_vpks_in(root) if unpacked else [path])]
        for folder in (_mod_roots(root) if unpacked else ()):
            label = folder.name if folder != root else name
            made.append(_pack(folder, label, work, language))
    if not made:
        raise ModArchiveError('Внутри нет ни VPK, ни папки мода (materials, models, sound...)')
    logger.info(f"мод из {path.name}: {[p.name for p in made]}")
    return made


def extract_zip(archive: Path, dest: Path) -> None:
    """Распаковка с проверками: путь внутри папки, размер и сжатие в пределах

    Raises:
        ModArchiveError: архив битый, опасный или слишком большой
    """
    try:
        zf = zipfile.ZipFile(archive)
    except (zipfile.BadZipFile, OSError) as exc:
        raise ModArchiveError(f'ZIP не открылся: {exc}') from exc
    with zf:
        infos = [i for i in zf.infolist() if not i.is_dir()]
        if len(infos) > MAX_FILES:
            raise ModArchiveError('В архиве слишком много файлов')
        total = sum(i.file_size for i in infos)
        packed = sum(i.compress_size for i in infos) or 1
        if total > MAX_TOTAL or total / packed > MAX_RATIO:
            raise ModArchiveError('Архив распаковывается в слишком большой объём')
        base = dest.resolve()
        for info in infos:
            target = (dest / info.filename).resolve()
            if base not in target.parents:
                raise ModArchiveError(f'Путь в архиве ведёт наружу: {info.filename}')
            target.parent.mkdir(parents=True, exist_ok=True)
            with zf.open(info) as src, open(target, 'wb') as out:
                shutil.copyfileobj(src, out)


def _vpks_in(root: Path) -> List[Path]:
    """VPK внутри: одиночные и `_dir.vpk` многотомных; сами тома - нет"""
    return sorted(p for p in root.rglob('*.vpk') if p.is_file() and not _CHUNK.search(p.name))


def _mod_roots(root: Path) -> List[Path]:
    """Папки, устроенные как мод в tf/custom: в них лежит materials, models...

    Внутрь найденного корня не спускаемся - его подпапки часть того же мода
    """
    found: List[Path] = []
    stack = [root]
    while stack:
        folder = stack.pop()
        children = [c for c in folder.iterdir() if c.is_dir()]
        if any(c.name.lower() in MOD_DIRS for c in children):
            found.append(folder)
            continue
        stack.extend(children)
    return sorted(found)


def _to_library(vpk_path: Path, work: Path, language: str) -> Path:
    """VPK - в библиотеку. Многотомный пересобирается одним файлом: библиотека
    копирует один файл, и тома остались бы позади"""
    from src.services import mod_library_service

    if not vpk_path.name.lower().endswith('_dir.vpk'):
        saved = mod_library_service.add(str(vpk_path))
        if saved is None:
            raise ModArchiveError(f'Не скопировать {vpk_path.name}')
        return saved
    import vpk as vpklib

    folder = work / f'unpack_{vpk_path.stem}'
    pak = vpklib.open(str(vpk_path))
    for inner in pak:
        target = (folder / inner).resolve()
        if folder.resolve() not in target.parents:
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(pak[inner].read())
    return _pack(folder, vpk_path.stem[:-len('_dir')], work, language)


def _pack(folder: Path, name: str, work: Path, language: str) -> Path:
    """Папка мода - одним VPK в библиотеку

    Пакуется копия: vpk.exe кладёт результат рядом с папкой, и с папкой
    человека (tf/custom/мод) он насорил бы прямо у него в игре
    """
    from src.services import mod_library_service
    from src.services.packaging_service import PackagingService

    safe = re.sub(r'[^\w.-]+', '_', name).strip('._') or 'mod'
    copy = work / 'pack' / safe
    if copy.exists():
        shutil.rmtree(copy)
    shutil.copytree(folder, copy, ignore=shutil.ignore_patterns('*.vpk'))
    built = PackagingService.pack_directory(copy, f'{safe}.vpk',
                                            export_folder=str(work / 'out'),
                                            language=language)
    saved = mod_library_service.add(built)
    if saved is None:
        raise ModArchiveError(f'Не скопировать {safe}.vpk')
    os.remove(built)
    return saved
