"""
Карта нормалей из картинки - одна на сборку, анимацию и 3D-превью

Не фильтр нормалей VTFLib: у него рельеф почти плоский (на плавном перепаде
±2-3 из 127, видна только зернистость сжатия). Реализация одна, и её же видно
в превью

Как строится:

* высота - яркость (светлое выпуклое, «Инвертировать» - наоборот);
* наклон - по трём масштабам сразу: мелкие детали, средние, крупные формы.
  Один масштаб ловит либо шум, либо ничего;
* оси - как ждёт Source: X+ Y- Z+ («DirectX»);
* если у материала в игре есть своя нормаль (нарисованная Valve), рельеф из
  картинки ложится ПОВЕРХ неё (reoriented normal mapping), а не вместо: иначе
  пропадали смоделированные фаски и швы. Её альфа сохраняется - у ~33
  материалов TF2 там маска блеска, и без неё предмет блестел целиком;
* у материала с `$phong` и `$basemapalphaphongmask` шейдер игры карту
  нормалей не читает вовсе (см. `phong_mask_in_base`). Чтобы рельеф появился,
  параметр снимается, а маска блеска переезжает из альфы основы в альфу
  нормали
"""

from __future__ import annotations

import os
import tempfile
from dataclasses import dataclass
from typing import Optional

import numpy as np
from PIL import Image

from src.shared.logging_config import get_logger

logger = get_logger(__name__)

#: Масштабы рельефа (во сколько раз уменьшена картинка) и их вес. Крупный
#: масштаб считается на уменьшенной картинке: его наклон «на пиксель» больше,
#: поэтому формы видны, а не тонут в мелочи
_SCALES = ((1, 1.0), (4, 0.45), (16, 0.2))
#: Сила 1.0 - рельеф заметный, но не «пластилин». Подобрано на текстурах
#: оружия TF2: средний наклон около 10°
_GAIN = 14.0
#: Опция сборки: маску блеска нормаль берёт из альфы картинки. Ставит её
#: `options_for` по VMT материала, человек её не видит
MASK_FROM_BASE = 'normal_mask_from_base'


@dataclass(frozen=True)
class NormalSettings:
    strength: float = 1.0
    invert: bool = False
    #: Класть рельеф поверх родной нормали материала, если она есть
    over_stock: bool = True
    #: Альфа нормали - альфа самой картинки: маска блеска переезжает из
    #: основы (см. `phong_mask_in_base`)
    mask_from_base: bool = False

    @classmethod
    def from_options(cls, options: Optional[dict]) -> "NormalSettings":
        o = options or {}
        try:
            strength = float(o.get('normal_strength', 1.0))
        except (TypeError, ValueError):
            strength = 1.0
        return cls(strength=min(max(strength, 0.0), 4.0),
                   invert=bool(o.get('normal_invert', False)),
                   # Галка страницы - «Заменить родной рельеф»: по умолчанию
                   # рельеф картинки ложится поверх родной нормали
                   over_stock=not o.get('normal_replace_stock', False),
                   mask_from_base=bool(o.get(MASK_FROM_BASE, False)))


def _height(rgb: np.ndarray, invert: bool) -> np.ndarray:
    """Яркость 0..1 (Rec. 709) как высота"""
    rgb = rgb[..., :3].astype(np.float32) / 255.0
    h = rgb[..., 0] * 0.2126 + rgb[..., 1] * 0.7152 + rgb[..., 2] * 0.0722
    return 1.0 - h if invert else h


def _sobel(h: np.ndarray):
    """(dh/dx, dh/dy) на пиксель; y - вниз по картинке"""
    p = np.pad(h, 1, mode='edge')
    dx = ((p[:-2, 2:] + 2 * p[1:-1, 2:] + p[2:, 2:])
          - (p[:-2, :-2] + 2 * p[1:-1, :-2] + p[2:, :-2])) / 8.0
    dy = ((p[2:, :-2] + 2 * p[2:, 1:-1] + p[2:, 2:])
          - (p[:-2, :-2] + 2 * p[:-2, 1:-1] + p[:-2, 2:])) / 8.0
    return dx, dy


def _resize(a: np.ndarray, w: int, h: int, resample=Image.BILINEAR) -> np.ndarray:
    return np.asarray(Image.fromarray(a.astype(np.float32), 'F').resize((w, h), resample))


def from_image(rgb: np.ndarray, strength: float = 1.0, invert: bool = False) -> np.ndarray:
    """Картинка (H×W×3|4, uint8) -> единичные нормали H×W×3 в осях Source"""
    h = _height(rgb, invert)
    rows, cols = h.shape
    # Мелкий масштаб - от ~1024 px: у картинки 2048 «одна деталь» шире пикселя
    unit = max(1, round(max(rows, cols) / 1024))
    gx = np.zeros_like(h)
    gy = np.zeros_like(h)
    for scale, weight in _SCALES:
        s = scale * unit
        if s == 1:
            dx, dy = _sobel(h)
        else:
            w2, h2 = max(2, cols // s), max(2, rows // s)
            small = _resize(h, w2, h2, Image.BOX)
            sdx, sdy = _sobel(small)
            dx, dy = _resize(sdx, cols, rows), _resize(sdy, cols, rows)
        gx += weight * dx
        gy += weight * dy
    # Наклон «на пиксель» у картинки 512 вдвое больше, чем у 1024 с тем же
    # рисунком: приводим к 1024, иначе сила зависела бы от разрешения сборки,
    # а превью (≤1024) расходилось бы с игрой
    k = _GAIN * float(strength) * (max(rows, cols) / 1024.0) / unit
    # Светлое выпуклое: у выпуклости слева нормаль смотрит влево (R < 128),
    # сверху - вверх, а это в осях Source G < 128
    n = np.dstack([-k * gx, -k * gy, np.ones_like(h)])
    n /= np.linalg.norm(n, axis=2, keepdims=True)
    return n


def decode(rgba: np.ndarray) -> np.ndarray:
    """Нормали из картинки нормалей (uint8) - единичные, в [-1, 1]"""
    n = rgba[..., :3].astype(np.float32) / 127.5 - 1.0
    length = np.linalg.norm(n, axis=2, keepdims=True)
    return n / np.maximum(length, 1e-6)


def blend(base: np.ndarray, detail: np.ndarray) -> np.ndarray:
    """Рельеф ``detail`` поверх ``base`` (reoriented normal mapping)

    Не сложение: сумма «сплющивает» оба рельефа. RNM поворачивает деталь по
    наклону основы - фаска остаётся фаской, узор ложится на неё
    """
    t = base + np.array([0.0, 0.0, 1.0], np.float32)
    u = detail * np.array([-1.0, -1.0, 1.0], np.float32)
    r = t * (np.sum(t * u, axis=2, keepdims=True) / np.maximum(t[..., 2:3], 1e-6)) - u
    # Крутой рельеф на крутой фаске в сумме даёт больше 90°: нормаль под
    # поверхностью игра осветила бы с изнанки
    r[..., 2] = np.maximum(r[..., 2], 0.0)
    return r / np.maximum(np.linalg.norm(r, axis=2, keepdims=True), 1e-6)


def encode(n: np.ndarray, alpha: Optional[np.ndarray] = None) -> np.ndarray:
    """Нормали -> RGBA uint8 (альфа - своя или сплошная)"""
    rgb = np.clip((n * 0.5 + 0.5) * 255.0 + 0.5, 0, 255).astype(np.uint8)
    a = alpha if alpha is not None else np.full(rgb.shape[:2], 255, np.uint8)
    return np.dstack([rgb, a.astype(np.uint8)])


def fit(rgba: np.ndarray, cols: int, rows: int, resample=Image.BILINEAR) -> np.ndarray:
    """Картинка H×W×C (uint8) в размере rows×cols, каждый канал отдельно

    Не `Image.resize` у RGBA: Pillow на время ресайза умножает цвет на альфу,
    а у текстур Source альфа - маска блеска, не прозрачность. Там, где маска
    ноль, цвет обнулялся: нормаль (0, 0, 0) смотрит под поверхность
    """
    if rgba.shape[:2] == (rows, cols):
        return rgba
    return np.dstack([np.asarray(Image.fromarray(rgba[..., i]).resize((cols, rows), resample))
                      for i in range(rgba.shape[2])])


def make(rgb: np.ndarray, settings: NormalSettings,
         stock: Optional[np.ndarray] = None) -> np.ndarray:
    """Карта нормалей RGBA для картинки ``rgb``; ``stock`` - родная нормаль (RGBA)"""
    n = from_image(rgb, settings.strength, settings.invert)
    alpha = None
    if stock is not None:
        rows, cols = n.shape[:2]
        stock = fit(stock, cols, rows)
        # Альфа родной нормали - маска блеска или отражения: без неё предмет
        # блестел бы весь
        alpha = stock[..., 3]
        if settings.over_stock:
            n = blend(decode(stock), n)
    if settings.mask_from_base:
        # Картинка без альфы - в игре её альфа единица: блеск по всему предмету
        alpha = rgb[..., 3] if rgb.shape[2] == 4 else None
    return encode(n, alpha)


def phong_mask_in_base(vmt_text: Optional[str]) -> bool:
    """Берёт ли материал маску блеска из альфы основы - и тогда не читает нормаль

    Шейдер оружия и шапок (Source SDK 2013, skin_ps20b.fxc):
    `tangentSpaceNormal = lerp(2 * normalTexel - 1, float3(0, 0, 1),
    g_fBaseMapAlphaPhongMask)`. При `$basemapalphaphongmask 1` нормаль
    плоская, что бы ни лежало в `$bumpmap`. Так устроены 263 из 371
    материалов c_items

    Прозрачный материал не в счёт: без параметра альфа основы стала бы у него
    прозрачностью (`alpha = baseColor.a * alpha` там же), и снимать параметр
    нельзя
    """
    from src.services import vmt_parse

    if not vmt_text:
        return False
    doc = vmt_parse.parse(vmt_text)
    if not (doc.flag('$phong') and doc.flag('$basemapalphaphongmask')):
        return False
    see_through = any(doc.flag(p) for p in ('$translucent', '$alphatest', '$additive'))
    # У этих двух альфа основы занята и в прозрачность не идёт
    alpha_taken = doc.flag('$selfillum') or doc.flag('$blendtintbybasealpha')
    return alpha_taken or not see_through


def options_for(vmt_text: Optional[str], options: Optional[dict]) -> dict:
    """Опции сборки нормали для материала с этим VMT"""
    options = dict(options or {})
    if options.get('normal') and phong_mask_in_base(vmt_text):
        options[MASK_FROM_BASE] = True
    return options


def take_phong_mask(vmt_path) -> bool:
    """Снимает `$basemapalphaphongmask`: маску блеска теперь несёт альфа
    нормали, собранной с `MASK_FROM_BASE`. True - параметр был и снят"""
    from src.services.vmt_service import VMTService

    try:
        with open(vmt_path, encoding='utf-8', errors='replace') as f:
            text = f.read()
    except OSError:
        return False
    if not phong_mask_in_base(text):
        return False
    done = VMTService.remove_param(str(vmt_path), '$basemapalphaphongmask')
    if done:
        logger.info(f'[normal] {os.path.basename(str(vmt_path))}: $basemapalphaphongmask снят, '
                    f'маска блеска в альфе нормали')
    return done


def rgba_from_vtf(data: bytes) -> Optional[np.ndarray]:
    """Первый кадр VTF -> RGBA uint8 (None, если не читается)"""
    from src.services.vtflib_wrapper import VTFLib

    fd, tmp = tempfile.mkstemp(suffix='.vtf', prefix='tf2sg_nrm_')
    try:
        with os.fdopen(fd, 'wb') as f:
            f.write(data)
        raw, w, h = VTFLib.read_vtf_as_rgba(tmp)
        return np.frombuffer(raw, np.uint8).reshape(h, w, 4).copy()
    except Exception as exc:                              # noqa: BLE001
        logger.warning(f'[normal] родная нормаль не читается: {exc}')
        return None
    finally:
        try:
            os.remove(tmp)
        except OSError:
            pass


def stock_normal(vmt_text: Optional[str], vpk_paths) -> Optional[np.ndarray]:
    """Родная нормаль материала по его VMT ($bumpmap) из VPK игры

    None и там, где игра её не рисует (`phong_mask_in_base`): рельеф картинки
    поверх неё показал бы то, чего в игре на предмете никогда не было
    """
    from src.services import vmt_parse
    from src.services.game_vpk_reader import GameVpkReader

    if not vmt_text or phong_mask_in_base(vmt_text):
        return None
    bump = vmt_parse.parse(vmt_text).path('bumpmap')
    paks = [p for p in (vpk_paths or []) if p]
    if not bump or not paks:
        return None
    reader = GameVpkReader(paks)
    try:
        data = reader.find_vtf_for_basetexture(bump)
    finally:
        reader.close()
    return rgba_from_vtf(data) if data else None


def vtf_format(base_format: str) -> str:
    """Формат VTF нормали: сжатая - DXT5 (как у Valve), иначе без потерь

    Формат базы не годится: DXT1 даёт на нормали блоки и теряет альфу, где
    у родной нормали маска блеска
    """
    name = (base_format or '').upper()
    return 'BGRA8888' if '888' in name else 'DXT5'
