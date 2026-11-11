"""
Какие модели игры рисуют текстуру: путь VTF -> MDL

Игра хранит связь только в одну сторону: модель называет свои материалы, а
материал - свою текстуру. Мод из одних текстур лежит по тем же путям, что и
текстуры игры, но путь модели не называет: в materials/.../c_items/ сотни
пушек вперемешку, Backburner рисует текстура `c_backburn`, огоньки гирлянд -
одна текстура на сотню моделей. Поэтому связь разворачивается целиком: каждая
модель игры -> её материалы ($cdmaterials + имя) -> $basetexture

Из MDL читается только список материалов (mdl_mesh.materials), без разбора
геометрии: вся игра - около 3 секунд. Таблица хранится до обновления игры
"""

from __future__ import annotations

import json
import os
import re
import threading
from typing import Any, Dict, Iterable, Optional, Sequence, Set

from src.services.mod_textures import texture_key
from src.shared.logging_config import get_logger
from src.shared.paths import data_dir

logger = get_logger(__name__)

_VERSION = 3
_lock = threading.Lock()
_memo: Dict[str, dict] = {}


def build(pak, items_text: str = '') -> dict:
    """{'users': {текстура: [MDL]}, 'vmts': {текстура: VMT}, 'items': [MDL из
    items_game]} по открытому VPK. VMT нужен моду из одних текстур: краску
    шапки (маска в альфе) задаёт материал игры, своего у мода нет"""
    from src.services.mdl_mesh import materials
    from src.services.mod_textures import vmt_references

    used: Dict[tuple, Set[str]] = {}
    for mdl in (p for p in pak if p.endswith('.mdl') and p.startswith('models/')):
        try:
            names, cds = materials(pak[mdl].read())
        except Exception:                                    # noqa: BLE001
            continue
        cds = tuple(c.strip('/').lower() for c in cds) + ('',)
        for name in names:
            used.setdefault((cds, name.lower()), set()).add(mdl.lower())

    users: Dict[str, Set[str]] = {}
    vmts: Dict[str, str] = {}
    refs_of: Dict[str, Optional[dict]] = {}
    for (cds, name), models in used.items():
        # Материал ищется как игра: первая папка $cdmaterials, где он есть
        for cd in cds:
            vmt = 'materials/' + '/'.join(p for p in (cd, name) if p) + '.vmt'
            if vmt not in refs_of:
                try:
                    text = pak[vmt].read().decode('utf-8', errors='replace')
                except KeyError:
                    continue
                refs_of[vmt] = vmt_references([text])
            refs = refs_of[vmt]
            # И служебные карты: мод из одной нормали или lightwarp тоже
            # перекрашивает модель, а не «ничего в игре»
            for key in refs['base'] | refs['service']:
                users.setdefault(key, set()).update(models)
            for key in refs['base']:
                vmts.setdefault(key, vmt)
            break
    items = {m.lower() for m in re.findall(r'"(models/[^"]+?\.mdl)"', items_text, re.I)}
    return {'users': {k: sorted(v) for k, v in users.items()}, 'vmts': vmts,
            'items': sorted(items)}


def _stamp(*paths: str) -> str:
    out = []
    for p in paths:
        try:
            st = os.stat(p)
            out.append(f'{st.st_size}:{st.st_mtime:.0f}')
        except OSError:
            out.append('-')
    return '|'.join(out)


def load(misc_vpk: str) -> dict:
    """Таблица игры: из памяти, из кэша на диске или собранная заново"""
    from src.data.weapon_model_index import tf2_root_from_misc_vpk

    root = tf2_root_from_misc_vpk(misc_vpk) or ''
    items_path = os.path.join(root, 'tf', 'scripts', 'items', 'items_game.txt')
    stamp = f'{_VERSION}|{_stamp(misc_vpk, items_path)}'
    with _lock:
        if _memo.get(misc_vpk, {}).get('stamp') == stamp:
            return _memo[misc_vpk]
        cache = data_dir() / 'cache' / 'texture_models.json'
        try:
            with open(cache, encoding='utf-8') as f:
                table = json.load(f)
        except (OSError, ValueError):
            table = {}
        if table.get('stamp') != stamp:
            table = _rebuild(misc_vpk, items_path, stamp, cache)
        _memo[misc_vpk] = table
        return table


def _rebuild(misc_vpk: str, items_path: str, stamp: str, cache) -> dict:
    from src.services.vpk_cache import open_vpk_cached

    pak = open_vpk_cached(misc_vpk)
    if not pak:
        return {'stamp': '', 'users': {}, 'vmts': {}, 'items': []}
    try:
        with open(items_path, encoding='utf-8', errors='replace') as f:
            items_text = f.read()
    except OSError:
        items_text = ''
    table = {'stamp': stamp, **build(pak, items_text)}
    logger.info(f"таблица текстур игры: {len(table['users'])} текстур")
    try:
        cache.parent.mkdir(parents=True, exist_ok=True)
        tmp = cache.with_suffix('.tmp')
        with open(tmp, 'w', encoding='utf-8') as f:
            json.dump(table, f)
        os.replace(tmp, cache)
    except OSError as exc:
        logger.warning(f"таблица текстур не сохранена: {exc}")
    return table


def matched(key: str, table: Dict[str, Any]) -> str:
    """Ключ таблицы для текстуры мода. Сверяется по концу пути: собранный мод
    лежит в папке-обходе (console/models/...), а игра знает его как models/..."""
    parts = key.split('/')
    for i in range(len(parts)):
        tail = '/'.join(parts[i:])
        if table.get(tail):
            return tail
    return ''


def by_tail(key: str, table: Dict[str, Any]) -> Any:
    """Запись текстуры в таблице (см. matched) или None"""
    return table.get(matched(key, table))


def vmt_for(vtf: str, table: dict) -> str:
    """VMT игры, который рисует эту текстуру, или пусто"""
    return by_tail(texture_key(vtf), table.get('vmts') or {}) or ''


def model_for(vtf_files: Iterable[str], base: Sequence[str], table: dict) -> str:
    """Модель игры, которую перекрашивает мод из одних текстур; пусто - такой нет

    `base` - основные текстуры мода (на что смотрит $basetexture). Из моделей,
    что их рисуют, берётся та, что рисует больше всего текстур мода: синяя и
    обычная вместе указывают на одну. Дальше - модель, названная как
    текстура (w_rocket для w_rocket01, а не гранатомёт с той же ракетой),
    потом с папкой ближе к текстуре, потом та, что есть у предметов игры (а
    не старая v_models), потом короче
    """
    users = table.get('users') or {}
    items = set(table.get('items') or ())
    # Пути игры, а не мода: у мода в папке-обходе (console/) близость папок
    # иначе не совпадала ни с одной моделью
    game = {v: matched(texture_key(v), users) for v in vtf_files}
    hits: Dict[str, int] = {}
    for key in filter(None, game.values()):
        for mdl in users[key]:
            hits[mdl] = hits.get(mdl, 0) + 1
    if not hits:
        return ''
    found = [game[v] for v in (base or vtf_files) if game.get(v)] or [
        k for k in game.values() if k]
    stems = [k.rsplit('/', 1)[-1] for k in found]

    def named(mdl: str) -> int:
        m = mdl.rsplit('/', 1)[-1][:-4]
        return max((2 if m == s else 1 if s.startswith(m) or m.startswith(s) else 0)
                   for s in stems)

    # Тело пулемётчика (player/hvyweapon/) рисует и рубашка-косметика: по
    # имени их не различить, а папки у тела ближе
    folders = [k.split('/')[:-1] for k in found]

    def near(mdl: str) -> int:
        parts = mdl.split('/')[:-1]
        return max(len(os.path.commonprefix([parts, f])) for f in folders)

    return max(hits, key=lambda m: (hits[m], named(m), near(m), m in items, -len(m), m))
