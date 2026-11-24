"""
Нетронутые текстуры в моде - ссылкой на игру, а не копией

Одно правило на всю сборку: VTF, который байт в байт совпадает с игровым,
в мод не кладётся, а VMT, смотревшие на него, переводятся на путь игры.
Стадии сборки по-прежнему пишут копию (BLU «как красная», «Скопировать
главную», нормаль из игровой текстуры читают её байты), а этот проход в
самом конце убирает все копии разом. Так не нужно, чтобы каждая стадия
сама решала, копировать игровую текстуру или ссылаться на неё

Копии копий (синяя пара из красной игровой) находятся по тем же байтам,
поэтому отслеживать, кто от кого скопирован, не нужно
"""

from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import Dict, Tuple

from src.shared.game_paths import texture_key
from src.shared.logging_config import get_logger

logger = get_logger(__name__)

_QUOTED = re.compile(r'"([^"\r\n]*)"')


def link_to_game(materials_root: Path, game_textures: Dict[str, str]) -> int:
    """
    Убирает из мода игровые VTF и переводит VMT на их путь в игре

    Args:
        materials_root: папка materials внутри мода.
        game_textures: {sha1 VTF: путь текстуры в игре} (MaterialSlots.put_game_vtf).

    Returns:
        Сколько VTF убрано
    """
    if not game_textures or not materials_root.is_dir():
        return 0
    moved = _game_copies(materials_root, game_textures)
    if not moved:
        return 0
    vmts = sorted(materials_root.rglob("*.vmt"))
    for vmt in vmts:
        _repoint(vmt, moved)
    # VMT, который сослался на копию так, что замена его не взяла, остаётся
    # с копией: лишний вес лучше фиолетового материала
    still_used = {key for vmt in vmts for key in moved if key in _refs(vmt)}
    removed = 0
    for key, (game, vtf) in moved.items():
        if key in still_used:
            logger.warning(f"[game-link] {vtf.name}: ссылку не перевести, копия остаётся")
            continue
        vtf.unlink()
        removed += 1
        logger.info(f"[game-link] {vtf.name} -> {game} (в моде не нужен)")
    return removed


def _game_copies(root: Path, game_textures: Dict[str, str]) -> Dict[str, Tuple[str, Path]]:
    """{путь VTF в моде без .vtf: (путь в игре, файл)} для копий игры"""
    out: Dict[str, Tuple[str, Path]] = {}
    for vtf in sorted(root.rglob("*.vtf")):
        try:
            digest = hashlib.sha1(vtf.read_bytes()).hexdigest()
        except OSError:
            continue
        game = game_textures.get(digest)
        if game:
            out[vtf.relative_to(root).with_suffix("").as_posix().lower()] = (game, vtf)
    return out


_norm = texture_key


def _read(vmt: Path) -> str:
    # Байтами: концы строк файла остаются как были
    try:
        return vmt.read_bytes().decode("utf-8", errors="replace")
    except OSError:
        return ""


def _repoint(vmt: Path, moved: Dict[str, Tuple[str, Path]]) -> None:
    text = _read(vmt)

    def swap(match):
        hit = moved.get(_norm(match.group(1)))
        return f'"{hit[0]}"' if hit else match.group(0)

    new = _QUOTED.sub(swap, text)
    if new != text:
        vmt.write_bytes(new.encode("utf-8"))


def _refs(vmt: Path) -> set:
    """Все пути-значения VMT, в кавычках и без"""
    return {_norm(token) for token in re.split(r'[\s"{}]+', _read(vmt)) if token}
