"""
Где лежит модель предмета внутри VPK игры - один ответ для превью, сборки,
извлечения и инструментов

Кандидаты зависят от вида предмета (src/data/item_kinds): у шапки путь из
items_game раскрывается в варианты (workshop, суффикс класса), у тела и маски
он точный, у рук и оружия - имя модели по раскладкам папок игры. Раньше это
правило жило в девяти местах, и каждое помнило свою часть
"""

from typing import Callable, List, Optional, Sequence, Tuple

from src.data.item_kinds import kind_of
from src.data.weapons import WEAPON_MDL_PATHS
from src.shared.logging_config import get_logger

logger = get_logger(__name__)


def mdl_candidates(mode: str, key: str = '', tf2_root: Optional[str] = None) -> List[str]:
    """Пути MDL в VPK по порядку приоритета. `key` - ключ модели (имя оружия,
    модель предплечья рук или путь MDL); пустой - по режиму (model_key_for)"""
    from src.domain.preview.model_key import model_key_for
    from src.services.tf2_paths import build_hat_mdl_candidates

    kind = kind_of(mode)
    key = key or model_key_for(mode) or ''
    if not key:
        return []
    if kind.is_hat:
        return build_hat_mdl_candidates(key)
    if kind.model_by_path or key.lower().endswith('.mdl'):
        return [key]
    return weapon_candidates(mode, key, tf2_root)


def weapon_candidates(mode: str, weapon_key: str, tf2_root: Optional[str] = None) -> List[str]:
    """Кандидаты модели оружия (и предплечья рук): точный путь из items_game,
    затем workshop_partner -> workshop -> стандарт -> c_items, с папкой и без,
    и папки классов"""
    # Ключ может быть незнакомым (модель из пользовательского VPK) - тогда
    # стандартная раскладка c_models вместо падения по KeyError
    base = WEAPON_MDL_PATHS.get(weapon_key, f"models/weapons/c_models/{weapon_key}/{weapon_key}.mdl")
    paths: List[str] = []
    if tf2_root:
        try:
            from src.data.weapon_model_index import resolve_weapon_mdl
            exact = resolve_weapon_mdl(weapon_key, tf2_root)
            if exact:
                paths.append(exact)
        except Exception as exc:                             # noqa: BLE001
            logger.debug(f"resolve_weapon_mdl({weapon_key}) не сработал: {exc}")
    folder, flat = f"/{weapon_key}/{weapon_key}.mdl", f"/{weapon_key}.mdl"
    for path in (base.replace("models/weapons/", "models/workshop_partner/weapons/"),
                 base.replace("models/weapons/", "models/workshop/weapons/"),
                 base,
                 base.replace("models/weapons/c_models/", "models/weapons/c_items/")):
        paths.append(path)
        if folder in path:
            paths.append(path.replace(folder, flat))
    # Последний шанс - папки классов (там обычно старьё)
    if "_" in mode:
        cls = mode.split("_", 1)[0]
        paths += [f"models/player/items/{cls}{folder}",
                  f"models/player/items/{cls}{flat}"]
    return paths


def first_existing(vpk_path: str, candidates: Sequence[str],
                   stop: Optional[Callable[[], bool]] = None,
                   on_step: Optional[Callable[[int, int], None]] = None
                   ) -> Tuple[Optional[str], Optional[Exception]]:
    """Первый кандидат, который есть в VPK: (путь | None, последняя ошибка)

    Только проверяет наличие, не распаковывая файлы. `stop` прерывает поиск
    (тогда путь None), `on_step(i, n)` - после каждой проверки"""
    from src.services.tf2_vpk_extract_service import TF2VPKExtractService

    last_error: Optional[Exception] = None
    for i, path in enumerate(candidates):
        if stop and stop():
            return None, last_error
        try:
            if TF2VPKExtractService.check_mdl_exists(vpk_path, path):
                logger.info(f"MDL найден: {path}")
                return path, None
        except Exception as exc:                             # noqa: BLE001
            logger.warning(f"Ошибка при проверке пути {path}: {exc}")
            last_error = exc
        if on_step:
            on_step(i + 1, len(candidates))
    return None, last_error


def not_found_error(t: dict, candidates: Sequence[str], vpk_path: str,
                    last_error: Optional[Exception] = None) -> str:
    """Сообщение «модель не найдена» со списком проверенных путей"""
    paths = "\n".join(f"  - {path}" for path in candidates)
    text = t.get("error_mdl_not_found", "MDL not found.\nPaths:\n{paths}\nVPK: {vpk_file}")
    message = text.format(paths=paths, vpk_file=vpk_path)
    return f"{message}\n{last_error}" if last_error else message
