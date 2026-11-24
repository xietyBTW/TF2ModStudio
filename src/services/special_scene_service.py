"""
Сцена спец-режимов: крит и эффекты смерти

Показывать в этих режимах нечего, кроме персонажа: у крита текстура висит
билбордом над ним, у эффекта смерти - ложится на него самого. Персонаж
процедурный (его строит вьювер), а из папки `tools/Model/<класс>` подхватывается
своя модель, если человек её туда положил

Вынесено из ``PreviewCritHitMixin``: правила «где искать модель» и «какая
текстура у эффекта по умолчанию» к виджетам отношения не имеют, а нужны и окну,
и странице
"""

from __future__ import annotations

import math
import os
from typing import List, Optional, Tuple

from src.shared.logging_config import get_logger
from src.shared.paths import data_dir

logger = get_logger(__name__)

#: Куда класть свою модель персонажа для сцены (по папке на класс)
#:
#: Папка ДАННЫХ, а не установки: модель сюда кладёт человек, а папку установки
#: обновление заменяет целиком (см. src/shared/paths.py). Пустых заготовок мы
#: не создаём - `scan` спокойно переживает отсутствие папки, а девять пустых
#: каталогов на всякий случай никому не помогают
MODEL_ROOT = str(data_dir() / 'tools' / 'Model')

_MODEL_EXTS = ('.obj', '.smd')
_TEXTURE_EXTS = ('.png', '.jpg', '.jpeg', '.bmp', '.tga', '.vtf', '.webp')


def find_scene_model(class_name: str = 'soldier') -> Tuple[str, str]:
    """
    (модель, текстура) для сцены - или пустые строки

    Сначала папка класса, потом общая: у людей обычно лежит одна модель на всех.
    Пусто - нормальный случай: вьювер нарисует процедурного персонажа
    """
    def scan(folder: str) -> Tuple[str, str]:
        if not os.path.isdir(folder):
            return '', ''
        model = texture = ''
        for name in sorted(os.listdir(folder)):
            if name.startswith('.'):
                continue
            low, full = name.lower(), os.path.join(folder, name)
            if not model and low.endswith(_MODEL_EXTS):
                model = full
            if not texture and low.endswith(_TEXTURE_EXTS):
                texture = full
        return model, texture

    model, texture = scan(os.path.join(MODEL_ROOT, (class_name or '').lower()))
    if model:
        return model, texture
    return scan(MODEL_ROOT)


def vtf_to_png(vtf_path: str) -> str:
    """VTF -> PNG во временный файл (общим декодером превью). Пустая
    строка, если не вышло"""
    from src.shared.file_utils import get_temp_file_path
    from src.services.vtf_preview_service import vtf_bytes_to_png

    try:
        with open(vtf_path, 'rb') as f:
            data = f.read()
    except OSError as exc:
        logger.warning(f"VTF→PNG сцены: {exc}")
        return ''
    png = str(get_temp_file_path(prefix='tf2_scene_tex_', suffix='.png'))
    return vtf_bytes_to_png(data, png) or ''


def game_texture(mode: str, vpk_paths: List[Optional[str]]) -> str:
    """
    Игровая текстура спец-режима как PNG: лёд, золото, огонь, крит

    Нужна дважды. Во-первых, для показа по умолчанию: пока человек не дал
    свою, сцена должна выглядеть так, как выглядит в игре. Во-вторых, для
    карточки - она стояла пустой, и было не видно, что именно заменяешь.
    Пусто - покажем без текстуры
    """
    try:
        tmp = _game_vtf_file(mode, vpk_paths)
        if tmp:
            try:
                return vtf_to_png(tmp)
            finally:
                _remove(tmp)
    except Exception as exc:                      # noqa: BLE001
        logger.debug(f"[спец-режим] игровую текстуру не достать: {exc}")
    return ''


def _game_vtf_file(mode: str, vpk_paths: List[Optional[str]]) -> str:
    """Игровой VTF спец-режима во временном файле; пусто - в игре его нет"""
    from src.services import vtf_preview_service as vps
    from src.services.vmt_service import VMTService
    from src.shared.file_utils import get_temp_file_path

    rel, _vmt, vtf = VMTService.get_weapon_relpaths(mode)
    folder = rel.replace('\\', '/').rstrip('/')
    candidates = [f"{folder}/{vtf}"]
    if vtf.lower() != vtf:
        candidates.append(f"{folder}/{vtf.lower()}")

    for pak in vps.open_vpks(vpk_paths):
        for candidate in candidates:
            try:
                data = pak[candidate].read()
            except KeyError:
                continue
            tmp = str(get_temp_file_path(prefix='tf2_deatheff_', suffix='.vtf'))
            with open(tmp, 'wb') as f:
                f.write(data)
            logger.info(f"[спец-режим] игровая текстура: {candidate}")
            return tmp
    return ''


def _remove(path: str) -> None:
    try:
        os.remove(path)
    except OSError:
        pass


#: Как игра кладёт огонь на горящего. Текстура подключена слоем `$detail` во
#: всех материалах игроков, шапок и оружия: `$detailscale 5` (плиткой, пять
#: повторов по развёртке), `$detailblendmode 6` (прибавляется к уже освещённому
#: цвету, а не затемняет его), кадры листает прокси AnimatedTexture, 30 в
#: секунду. Сила слоя - прокси BurnLevel, на пике единица
FIRE_SCALE = 5
FIRE_FPS = 30


def fire_overlay(vpk_paths: List[Optional[str]]) -> dict:
    """
    Игровой огонь для превью: все кадры одним листом и как его показывать

    Кадров в игре 121 по 64 пикселя. Отдельными файлами это сотня запросов
    на каждое открытие режима, поэтому они склеены в одну картинку сеткой, а
    вьювер режет её обратно

    Returns:
        {atlas, cols, rows, count, fps, scale} или пустой словарь
    """
    try:
        import numpy as np

        from src.services import fast_png
        from src.services.vtflib_wrapper import VTFLib
        from src.shared.file_utils import get_temp_file_path

        tmp = _game_vtf_file('death_fire', vpk_paths)
        if not tmp:
            return {}
        try:
            frames, width, height = VTFLib.read_vtf_all_frames(tmp)
        finally:
            _remove(tmp)
        if not frames:
            return {}
        cols = math.ceil(math.sqrt(len(frames)))
        rows = math.ceil(len(frames) / cols)
        sheet = np.zeros((rows * height, cols * width, 4), np.uint8)
        for i, rgba in enumerate(frames):
            top, left = (i // cols) * height, (i % cols) * width
            sheet[top:top + height, left:left + width] = (
                np.frombuffer(rgba, np.uint8).reshape(height, width, 4))
        atlas = str(get_temp_file_path(prefix='tf2_deatheff_', suffix='.png'))
        with open(atlas, 'wb') as f:
            f.write(fast_png.encode_rgba(sheet.tobytes(), cols * width, rows * height))
        return {'atlas': atlas, 'cols': cols, 'rows': rows, 'count': len(frames),
                'fps': FIRE_FPS, 'scale': FIRE_SCALE}
    except Exception as exc:                      # noqa: BLE001
        logger.warning(f"[спец-режим] кадры огня не собраны: {exc}")
        return {}
