"""Инструменты: библиотека модов, извлечение, экспорт, объединение VPK"""

from __future__ import annotations

from typing import Dict, List, Optional

from src.app.api._common import _lang, endpoint, logger


@endpoint
def mod_library() -> List[dict]:
    """Что лежит в библиотеке модов (новые сверху)"""
    from src.services import mod_library_service
    return mod_library_service.items()


@endpoint
def mod_icon(name: str = '') -> Dict[str, object]:
    """
    Обложка мода - его основная текстура, при первом запросе строится

    Отдельным вызовом, а не в списке: декодировать VTF всей библиотеки ради
    открытия каталога незачем, а карточки и без обложек показываются сразу
    """
    from src.services import mod_library_service

    path = mod_library_service.icon(name)
    return {'name': name, 'icon': str(path) if path else ''}


@endpoint
def add_mod(path: str = '') -> Dict[str, object]:
    """Кладёт открытый мод в библиотеку и отдаёт его постоянный путь"""
    from src.services import mod_library_service

    saved = mod_library_service.add(path)
    if saved is None:
        return {'error': 'VPK-файл не найден'}
    return {'name': saved.name, 'path': str(saved)}


@endpoint
def import_mod(path: str = '', lang: str = '') -> Dict[str, object]:
    """ZIP, папка мода или многотомный VPK - в библиотеку отдельными VPK:
    {'mods': [{name, path}]}, по одному на найденный внутри мод"""
    from src.services import mod_archive
    from src.shared.exceptions import RequiredFileMissingError, VPKCreationError

    if not path:
        return {'error': 'Файл или папка не найдены'}
    try:
        made = mod_archive.import_mod(path, _lang(lang))
    except mod_archive.ModArchiveError as exc:
        return {'error': str(exc)}
    except (VPKCreationError, RequiredFileMissingError, OSError) as exc:
        logger.warning(f"мод не упакован: {path}: {exc}", exc_info=True)
        return {'error': 'Не удалось упаковать мод в VPK'}
    return {'mods': [{'name': p.name, 'path': str(p)} for p in made]}


@endpoint
def remove_mod(name: str = '') -> Dict[str, object]:
    """Удаляет мод из библиотеки. Принимается только ИМЯ файла в ней"""
    from src.services import mod_library_service

    if not mod_library_service.remove(name):
        return {'error': f'«{name}» в библиотеке нет'}
    return {'removed': name}


@endpoint
def load_vpk_mod(path: str = '', lang: str = '',
                 model: str = '') -> Dict[str, object]:
    """Показывает чужой мод из VPK: его модель (или выбранную `model` -
    путь MDL внутри VPK) и его текстуры"""
    from src.app.session import session

    lang = _lang(lang)
    return session().load_vpk_mod(path, lang=lang, model=model)


@endpoint
def vpk_mod_models(path: str = '') -> Dict[str, object]:
    """Модели внутри VPK-мода: из них человек выбирает, какие показать"""
    import os

    from src.services import vpk_mod_models as models

    if not path or not os.path.isfile(path):
        return {'error': 'VPK-файл не найден'}
    try:
        return {'models': models.list_models(path)}
    except Exception as exc:                                  # noqa: BLE001
        logger.warning(f"модели мода не прочитаны: {path}: {exc}")
        return {'error': 'VPK не открылся'}


@endpoint
def mod_target(path: str = '', model: str = '', lang: str = '') -> Dict[str, object]:
    """
    Что заменяет мод: {mdl, kind, hat}. Страница узнаёт это ДО разбора мода:
    мод-шапка открывается на странице шапок, и раздел меняется раньше
    загрузки (смена раздела гасит превью)

    `hat` - строка каталога шапок, если мод заменяет косметику
    """
    import os

    from src.app import mod_hat
    from src.app.session import session
    from src.services import vpk_mod_models as models

    if not path or not os.path.isfile(path):
        return {'error': 'VPK-файл не найден'}
    paths = session().tf2_paths()
    try:
        import vpk as vpklib
        pak = vpklib.open(path)
        real = set(models.real_models(pak))
        files = [f for f in pak if not f.lower().endswith('.mdl') or f in real]
        # VMT нужны только моду без модели: по ним видно, какая текстура основная
        vmts = {} if any(f.lower().endswith('.mdl') for f in files) else {
            f: pak[f].read().decode('utf-8', errors='replace')
            for f in files if f.lower().endswith('.vmt')}
    except Exception as exc:                                  # noqa: BLE001
        logger.warning(f"мод не прочитан: {path}: {exc}")
        return {'error': 'VPK не открылся'}
    # Отказ - до смены раздела: страница не должна стирать показанное ради
    # мода, который всё равно не откроется
    why = models.why_not_shown(files, _lang(lang))
    if why:
        return {'error': why}
    mdl, _own = models.target(files, vmts, model,
                              '' if 'error' in paths else paths['misc_vpk'])
    kind = models.kind_of(mdl) if mdl else ''
    return {'mdl': mdl, 'kind': kind,
            'hat': mod_hat.catalog_row(mdl, _lang(lang)) if kind == 'cosmetic' else None}


@endpoint
def extract_model(lang: str = '') -> Dict[str, object]:
    """Декомпилирует модель, список файлов приходит событием extract_files"""
    from src.app.session import session

    lang = _lang(lang)
    return session().tools.extract_model(lang=lang)


@endpoint
def export_model_files(files: Optional[List[str]] = None,
                       lang: str = '') -> Dict[str, object]:
    """Сохраняет выбранные файлы модели (пустой список - отказ и уборка)"""
    from src.app.session import session

    lang = _lang(lang)
    return session().tools.export_model_files(files, lang=lang)


@endpoint
def extract_texture(textures: Optional[List[str]] = None,
                    lang: str = '') -> Dict[str, object]:
    """Извлекает оригинальные текстуры предмета в папку экспорта"""
    from src.app.session import session

    lang = _lang(lang)
    return session().tools.extract_texture(textures, lang=lang)


@endpoint
def export_card_texture(material: str, original: bool = False) -> Dict[str, object]:
    """Текстуру карточки (или её игровой оригинал) - в папку экспорта"""
    from src.app.session import session
    return session().tools.export_card_texture(material, original)


@endpoint
def export_vpks() -> List[str]:
    """Собранные моды в папке экспорта"""
    from src.app.session import session
    return session().tools.export_vpks()


@endpoint
def merge_candidates() -> List[dict]:
    """Моды папки экспорта для окна объединения: имя, размер, что внутри"""
    from src.app.session import session
    return session().tools.merge_candidates()


@endpoint
def merge_check(files: Optional[List[str]] = None) -> Dict[str, object]:
    """Где выбранные моды пересекаются; порядок `files` - приоритет"""
    from src.app.session import session
    return session().tools.merge_check(files)


@endpoint
def merge_vpk(files: Optional[List[str]] = None, name: str = '',
              confirmed: bool = False, lang: str = '') -> Dict[str, object]:
    """Сливает выбранные моды в один VPK"""
    from src.app.session import session

    lang = _lang(lang)
    return session().tools.merge_vpk(files, name, confirmed=confirmed, lang=lang)


@endpoint
def export_uv(size: int = 1024) -> Dict[str, object]:
    """Рисует UV-шаблон модели в папку экспорта. Путь придёт событием"""
    from src.app.session import session
    return session().export_uv(size)
