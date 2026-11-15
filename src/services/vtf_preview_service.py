"""
Утилиты превью VTF: открыть VPK, прочитать файл, декодировать VTF -> PNG

Связка «temp .vtf -> VTFLib.read_vtf_all_frames -> fast_png -> .png»
живёт здесь одна, чтобы не повторяться по воркерам
"""

import hashlib
import os
import struct
import tempfile
import threading
from collections import OrderedDict
from typing import List, Optional

from src.services import fast_png, preview_disk_cache, vmt_parse
from src.shared.logging_config import get_logger

logger = get_logger(__name__)

#: Уровень сжатия PNG там, где превью пишет Pillow (краска, vmt_tint). Замер на
#: стоковой текстуре 1024x1024: уровень 6 (умолчание Pillow) - 0.18 с и 0.7 МБ,
#: уровень 3 - 0.07 с и 0.8 МБ, уровень 1 - 0.05 с и 1.2 МБ. Сами текстуры из
#: VTF кодирует fast_png
PREVIEW_PNG_COMPRESS = 3


def open_vpks(paths: List[Optional[str]]) -> list:
    """Открывает существующие VPK из списка путей (несуществующие/битые пропускает)

    Хэндлы берутся из общего кэша (один разбор каталога на запуск) и
    принадлежат ему - закрывать их нельзя. Использовать только для ИГРОВЫХ
    VPK: кэш держит файл открытым до конца работы приложения, для временных
    пользовательских VPK это мешало бы их удалению
    """
    from src.services.vpk_cache import open_vpk_cached
    paks: list = []
    for p in paths:
        if p and os.path.exists(p):
            try:
                pak = open_vpk_cached(p)
                if pak is not None:
                    paks.append(pak)
            except Exception as exc:
                logger.debug(f"[VTF] не удалось открыть VPK {p}: {exc}")
    return paks


def read_from_vpks(paks: list, vpk_path: str) -> Optional[bytes]:
    """Возвращает байты файла по пути внутри первого VPK, где он есть"""
    for pak in paks:
        try:
            return pak[vpk_path].read()
        except KeyError:
            continue
        except Exception:
            continue
    return None


def parse_animated_framerate(vmt_content: str) -> Optional[float]:
    """animatedtextureframerate из текста VMT (None если ключа нет)

    Параметр лежит внутри прокси AnimatedTexture, поэтому ищется по всему
    дереву материала (разбор - общий, vmt_parse)
    """
    return vmt_parse.animated_framerate(vmt_content)


def read_vmt_framerate(pak, vmt_paths: List[str], default: float = 15.0) -> float:
    """animatedtextureframerate из первого ЧИТАЕМОГО VMT в pak; default если нет

    Первый успешно прочитанный VMT определяет результат: нашли framerate -> он;
    VMT есть, но без ключа -> default
    """
    if pak is None:
        return default
    for path in vmt_paths:
        try:
            content = pak[path].read().decode("utf-8", errors="replace")
        except KeyError:
            continue
        except Exception:
            continue
        fps = parse_animated_framerate(content)
        return fps if fps is not None else default
    return default


#: Готовые PNG последних текстур: {(отпечаток VTF, все кадры?): [байты PNG]}.
#: Каталог щёлкают туда-обратно, а декодировать VTF и кодировать PNG 2048 -
#: почти 0,2 с на текстуру. Ключ - содержимое, а не путь: та же картинка из
#: другого архива или мода найдётся, изменённая - нет
_png_cache: "OrderedDict[tuple, List[bytes]]" = OrderedDict()
_png_cache_size = 0
_PNG_CACHE_LIMIT = 64 * 1024 * 1024
_png_lock = threading.Lock()


def clear_png_cache() -> None:
    global _png_cache_size
    with _png_lock:
        _png_cache.clear()
        _png_cache_size = 0


def _decode_pngs(data: bytes, tmp_dir: str, label: str, all_frames: bool) -> List[bytes]:
    """PNG первого или всех кадров VTF; пусто, если не декодировался"""
    key = (hashlib.blake2b(data, digest_size=16).digest(), all_frames)
    with _png_lock:
        got = _png_cache.get(key)
        if got is not None:
            _png_cache.move_to_end(key)
            return got

    disk_key = key[0] + (b"\x01" if all_frames else b"\x00")
    kept = _unpack(preview_disk_cache.get("png", disk_key))
    if kept:
        _remember(key, kept)
        return kept

    from src.services.vtflib_wrapper import VTFLib

    os.makedirs(tmp_dir, exist_ok=True)
    tmp_vtf = os.path.join(tmp_dir, f"_tmp_{label}.vtf")
    try:
        with open(tmp_vtf, "wb") as f:
            f.write(data)
        frames, w, h = VTFLib.read_vtf_all_frames(tmp_vtf)
    except Exception as exc:
        logger.warning(f"[VTF] декодирование не удалось ({label}): {exc}")
        return []
    finally:
        try:
            os.remove(tmp_vtf)
        except OSError:
            pass
    pngs = [fast_png.encode_rgba(rgba, w, h)
            for rgba in (frames if all_frames else frames[:1])]
    _remember(key, pngs)
    if pngs:
        preview_disk_cache.put("png", disk_key, _pack(pngs))
    return pngs


def _remember(key: tuple, pngs: List[bytes]) -> None:
    global _png_cache_size
    with _png_lock:
        if key in _png_cache:
            return
        _png_cache[key] = pngs
        _png_cache_size += sum(map(len, pngs))
        while _png_cache_size > _PNG_CACHE_LIMIT and len(_png_cache) > 1:
            _old, dropped = _png_cache.popitem(last=False)
            _png_cache_size -= sum(map(len, dropped))


def _pack(pngs: List[bytes]) -> bytes:
    """Кадры одной записью: перед каждым его длина"""
    return b"".join(struct.pack("<I", len(png)) + png for png in pngs)


def _unpack(blob: Optional[bytes]) -> List[bytes]:
    """Кадры из записи; пусто, если её нет или она оборвана"""
    pngs: List[bytes] = []
    at = 0
    while blob and at < len(blob):
        if at + 4 > len(blob):
            return []
        size = struct.unpack_from("<I", blob, at)[0]
        at += 4
        if size == 0 or at + size > len(blob):
            return []
        pngs.append(blob[at:at + size])
        at += size
    return pngs


def vtf_bytes_to_png(data: Optional[bytes], out_png_path: str,
                     tmp_dir: Optional[str] = None) -> Optional[str]:
    """
    Декодирует байты VTF и сохраняет первый кадр как RGBA-PNG в out_png_path.
    Возвращает out_png_path или None при ошибке/пустых данных
    """
    if not data:
        return None
    tmp_dir = tmp_dir or os.path.dirname(out_png_path) or tempfile.gettempdir()
    pngs = _decode_pngs(data, tmp_dir, os.path.basename(out_png_path), all_frames=False)
    if not pngs:
        return None
    with open(out_png_path, "wb") as f:
        f.write(pngs[0])
    return out_png_path


def vtf_bytes_to_frame_pngs(data: Optional[bytes], out_dir: str, base_name: str,
                            tmp_dir: Optional[str] = None) -> List[str]:
    """
    Декодирует VTF и сохраняет ВСЕ кадры как PNG (для анимированных текстур).
    Один кадр -> {base}.png; несколько -> {base}_000.png, {base}_001.png, …
    Возвращает список путей по порядку (пустой при ошибке/нет кадров)
    """
    if not data:
        return []
    os.makedirs(out_dir, exist_ok=True)
    pngs = _decode_pngs(data, tmp_dir or out_dir, base_name, all_frames=True)
    multi = len(pngs) > 1
    paths: List[str] = []
    for i, png in enumerate(pngs):
        name = f"{base_name}_{i:03d}.png" if multi else f"{base_name}.png"
        path = os.path.join(out_dir, name)
        with open(path, "wb") as f:
            f.write(png)
        paths.append(path)
    return paths
