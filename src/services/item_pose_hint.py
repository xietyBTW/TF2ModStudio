"""
Как положить предмет в кадре: подсказка сторон для viewer_item_pose.js

Своего «верха» у модели оружия нет: c_models крепятся к кости руки, и в
сцене ствол смотрит вверх, а клинок вбок. Где у предмета перёд и верх, игра
знает сама: иконку рюкзака она снимает камерой `icon_camera` из модели
(UpdateCameraForIcon в item_model_panel.cpp). Её оси и есть подсказка: ствол
на иконке смотрит влево, то есть в сторону «left» камеры

Нет такой камеры, но модель висит на `weapon_bone` - стороны как у
большинства оружия в руке (HAND_FRAME). Нет и кости - это не ручной предмет
(аптечка, реквизит насмешки, тело класса): он и так стоит как в мире, и
подсказки нет

Векторы - в осях OBJ вьювера, тот же перевод, что у smd_to_obj для оружия:
Source (x, y, z) -> (x, z, -y)
"""

from __future__ import annotations

import functools
from pathlib import Path
from typing import Dict, List, Optional

from src.services import model_attachments as ma
from src.shared.logging_config import get_logger

logger = get_logger(__name__)

#: Камера иконки рюкзака в модели предмета
ICON_CAMERA = "icon_camera"
#: Кость руки, на которой висит оружие
HAND_BONE = "weapon_bone"

#: Стороны оружия в руке без своей камеры: ствол и остриё в +Y, верх в -Z.
#: Замерено на обрезе, ракетомёте, ноже и снайперке
HAND_FRAME: Dict[str, List[float]] = {"forward": [0.0, 1.0, 0.0], "up": [0.0, 0.0, -1.0]}

#: Ниже этого косинуса между взглядом камеры иконки и направлением на центр
#: модели камере не верим. Порог с запасом: часть модели в reference SMD
#: (бодигруппы) сдвигает центр
CAMERA_MIN = 0.8


def _to_obj(v) -> List[float]:
    return [v[0], v[2], -v[1]]


def _column(m: ma.Matrix3x4, i: int) -> List[float]:
    return [m[0][i], m[1][i], m[2][i]]


def _mesh_center(smd_text: str) -> Optional[List[float]]:
    """Центр габаритов треугольников SMD в осях Source, None - их нет"""
    lo, hi = [float("inf")] * 3, [float("-inf")] * 3
    lines = iter(smd_text.splitlines())
    for line in lines:
        if line.strip() == "triangles":
            break
    for line in lines:
        parts = line.split()
        if len(parts) < 4:
            if line.strip() == "end":
                break
            continue
        try:
            v = [float(parts[1]), float(parts[2]), float(parts[3])]
        except ValueError:
            continue                              # строка материала
        for k in range(3):
            lo[k], hi[k] = min(lo[k], v[k]), max(hi[k], v[k])
    return None if lo[0] > hi[0] else [(lo[k] + hi[k]) / 2 for k in range(3)]


def _looks_at(pos, forward, center: Optional[List[float]]) -> bool:
    """Смотрит ли камера на модель: у Помсона камера в модели глядит мимо
    (косинус -0,38 против 0,98-1,00 у остальных), иконку снимали не ею"""
    if center is None:
        return True
    d = [center[k] - pos[k] for k in range(3)]
    n = sum(x * x for x in d) ** 0.5
    return n == 0 or sum(forward[k] * d[k] for k in range(3)) / n >= CAMERA_MIN


@functools.lru_cache(maxsize=64)
def worn_on_player(qc_path: str) -> bool:
    """
    Предмет из таблицы оружия, который игра надевает на тело: ранец знамени,
    Razorback, ботинки, перчатки

    В руку такой не берут (нет weapon_bone) и иконку с него не снимают (нет
    icon_camera), зато кости - скелета игрока, и собран он против него, верхом
    по +Y. Показывать его надо как шапку - поставив на игрока (cosmetic_pose):
    осями оружия он ложился на спину, и кадр смотрел на него сверху
    """
    from src.data.player_skeleton import BONES

    try:
        if any(a.name.lower() == ICON_CAMERA for a in ma.attachments_from_qc(qc_path)):
            return False
        smd = ma.reference_smd_for_qc(qc_path)
        if not smd:
            return False
        names = {n.lower() for n in ma.parse_smd_bind_pose(
            Path(smd).read_text(encoding="utf-8", errors="ignore"))}
    except (OSError, ValueError):
        return False
    return HAND_BONE not in names and any(b.lower() in names for b in BONES)


def for_weapon(weapon: str) -> Optional[Dict[str, List[float]]]:
    """
    Подсказка для оружия в кадре или None (не оружие, модели нет в кэше)

    Стороны берутся у игрового оружия: своя модель и MDL мода сделаны под ту
    же кость руки, а у своей вьювер кладёт её по призраку оригинала
    """
    if not weapon:
        return None
    from src.services import decompile_cache

    qc = decompile_cache.find_cached_qc_for_weapon(weapon)
    return pose_hint(qc) if qc else None


def shown_on_player(kind, model) -> bool:
    """Ставить ли модель превью на игрока: шапку всегда, из таблицы оружия -
    надеваемое. model - разобранная модель с qc_path или пусто"""
    if kind.worn_on_player:
        return True
    return bool(kind.is_weapon and model and worn_on_player(model.qc_path))


@functools.lru_cache(maxsize=64)
def pose_hint(qc_path: str) -> Optional[Dict[str, List[float]]]:
    """
    {forward, up[, view]} для itemPose или None - модель не трогать

    forward - куда смотрит ствол, up - верх, view - куда смотрит камера
    иконки (только у модели со своей камерой, если та смотрит на модель)
    """
    try:
        smd = ma.reference_smd_for_qc(qc_path)
        text = Path(smd).read_text(encoding="utf-8", errors="ignore") if smd else ""
        center = _mesh_center(text)
        for a in ma.attachments_from_qc(qc_path):
            if a.name.lower() != ICON_CAMERA:
                continue
            # Столбцы матрицы Source: forward, left, up камеры
            m = ma.angle_matrix(*a.angles)
            if _looks_at(a.pos, _column(m, 0), center):
                return {"forward": _to_obj(_column(m, 1)),
                        "up": _to_obj(_column(m, 2)),
                        "view": _to_obj(_column(m, 0))}
            logger.debug(f"[pose] {qc_path}: icon_camera смотрит мимо модели")
        if any(name.lower() == HAND_BONE for name in ma.parse_smd_bind_pose(text)):
            return dict(HAND_FRAME)
    except (OSError, ValueError) as exc:
        logger.debug(f"поза предмета не определена ({qc_path}): {exc}")
    return None
