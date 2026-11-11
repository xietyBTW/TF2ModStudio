"""
Мод-шапка: чужой мод, который заменяет косметику

Мод остаётся модом (собирается целиком, `build_custom_mod`), но показывается
как шапка, которую он заменяет: на голове, на странице шапок, на персонаже.
Что это за шапка, говорит путь модели (vpk_mod_models.target), а классы и что
она прячет у персонажа - строка каталога с тем же путём
"""

from __future__ import annotations

from typing import Any, Dict, Optional


def is_hat(preview) -> bool:
    """Показан мод, и заменяет он косметику"""
    return bool(preview.custom_vpk_mode) and preview.custom_vpk_kind == 'cosmetic'


def _norm(path) -> str:
    return str(path or '').replace('\\', '/').lower()


def models_by_class(item, shown: str, own: bool) -> Dict[str, str]:
    """
    {класс: модель} для сцены «На персонаже»

    `item` - строка каталога (HatItem) или None, `shown` - путь показанной
    модели. Покласcовые модели берутся из того набора (предмета или стиля), где
    она есть. Своя модель мода заменяет модель только своих классов: у
    остальных в игре осталась бы игровая
    """
    if item is None:
        return {}
    sets = [dict(item.per_class_models or {})]
    sets += [dict(st.get('per_class_models') or {}) for st in item.styles or ()]
    models = next((m for m in sets if _norm(shown) in map(_norm, m.values())), None)
    if models is None:
        models = {c: shown for c in item.classes}
    if own:
        models = {c: m for c, m in models.items() if _norm(m) == _norm(shown)}
    return models


def scene_args(host, tf2_root: str, lang: str) -> Dict[str, Any]:
    """Аргументы `PreviewController.load_wear` для мода-шапки либо {'error': …}"""
    p = host.preview
    item = host._hat_catalog_item(tf2_root, lang, {p.custom_vpk_mdl})
    models = models_by_class(item, p.custom_vpk_mdl, own=bool(p.custom_vpk_smd))
    if not models:
        return {'error': 'Не удалось понять, какой класс носит эту шапку'}
    return {
        'hat_models': models,
        'hidden_bodygroups': dict(getattr(item, 'hidden_bodygroups', None) or {}),
        # Своя модель мода сливается со скелетом игровой шапки, как в сборке
        'custom_smd': p.custom_vpk_smd or '',
        'custom_keep': True,
        # Файлы мода - первыми: текстуры и свойства его материалов
        'mod_vpk_path': host._vpk_mod_path or '',
    }


def catalog_row(mdl: str, lang: str) -> Optional[dict]:
    """Строка каталога шапок с этой моделью (как у hats()) или None"""
    from src.app.api.hat_catalog import hat_item

    return hat_item(mdl, lang) or None
