"""
Одна текстура карточки - в папку экспорта

Источник - картинка, которую приложение уже показывает: файл на диске или
байты PNG. VTF здесь не пишем: текстуру карточки выгружают, чтобы открыть в
графическом редакторе, поэтому при формате экспорта VTF сохраняем PNG
"""

from __future__ import annotations

import io
import re
from pathlib import Path
from typing import Union

from PIL import Image

_EXT = {'PNG': 'png', 'TGA': 'tga', 'JPG': 'jpg', 'JPEG': 'jpg'}


def file_stem(name: str) -> str:
    """Имя файла из имени материала: без папок, расширения и запрещённых знаков"""
    base = re.split(r'[\\/]', name or '')[-1]
    base = re.sub(r'\.(vmt|vtf|png)$', '', base, flags=re.IGNORECASE)
    base = re.sub(r'[<>:"|?*\x00-\x1f]', '_', base).strip(' .')
    return base or 'texture'


def _free_path(folder: Path, stem: str, ext: str) -> Path:
    """Не затираем прошлый экспорт: второй файл получает номер"""
    path = folder / f'{stem}.{ext}'
    n = 2
    while path.exists():
        path = folder / f'{stem}_{n}.{ext}'
        n += 1
    return path


def _open(source: Union[str, bytes]) -> Image.Image:
    if isinstance(source, bytes):
        return Image.open(io.BytesIO(source))
    if source.lower().endswith('.vtf'):
        from src.services.vtflib_wrapper import VTFLib
        rgba, w, h = VTFLib.read_vtf_as_rgba(source)
        return Image.frombytes('RGBA', (w, h), rgba)
    return Image.open(source)


def export_image(source: Union[str, bytes], folder, name: str, fmt: str = 'PNG') -> Path:
    """Сохраняет картинку как `<имя>.<формат>` и отдаёт путь к файлу"""
    ext = _EXT.get((fmt or '').upper(), 'png')
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    target = _free_path(folder, file_stem(name), ext)
    with _open(source) as img:
        if ext == 'jpg':
            img.convert('RGB').save(target, quality=95)
        else:
            img.convert('RGBA').save(target)
    return target
