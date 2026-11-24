"""
Пер-текстурные настройки (оверрайды поверх глобальных)

Модель «глобальное по умолчанию + разреженный оверрайд»:
  • для материала НЕТ записи  -> используются глобальные настройки сборки;
  • для материала ЕСТЬ запись  -> её поля переопределяют глобальные

Важно по UX:
  • простое открытие настроек материала запись НЕ создаёт (UI читает текущее
    состояние, не мутирует);
  • запись появляется только при явном действии (тумблер «свои настройки» off /
    изменение поля);
  • возврат к глобальному - удаление записи (revert)

Запись (override) может быть частичной: какие ключи заданы, те и переопределяют.
Ключи: 'size' (tuple|list), 'format' (str), 'flags' (list), 'options' (dict)
"""

_OVERRIDABLE_KEYS = ('size', 'format', 'flags', 'options')


def own_settings(settings: dict, name: str, main: str = ''):
    """
    Свои настройки материала `name` из записанных по карточкам (или None)

    Карточка и материал модели называются не всегда одинаково: у своей
    модели карточка `Material.001`, а studiomdl собирает её как
    `material_001`; у модели с одним материалом имени главного страница не
    знает и хранит его настройки под пустым ключом (`main` - имя главного)
    """
    from src.services.part_materials import model_name
    from src.shared.team_names import is_blue, team_form

    settings = settings or {}
    own = settings.get(name)
    if own is None:
        own = next((v for k, v in settings.items()
                    if k and model_name(k) == model_name(name)), None)
    if own is None and name and name == main:
        own = settings.get('')
    if own is None and is_blue(name):
        # Синий материал собирается настройками своей красной карточки:
        # синие правки карточки хранят под красной (`c_x_blue_gold` -> `c_x_gold`)
        base = team_form(name)[0]
        own = next((v for k, v in settings.items()
                    if k and not is_blue(k) and team_form(k)[0] == base), None)
    return own


def effective_settings(global_settings: dict, override: dict = None) -> dict:
    """
    Возвращает эффективные настройки материала: глобальные, переопределённые
    полями оверрайда (если он есть). Глобальные не мутируются
    """
    eff = dict(global_settings or {})
    if override:
        for k in _OVERRIDABLE_KEYS:
            if k in override and override[k] is not None:
                eff[k] = override[k]
    return eff


def vtf_settings(size, format_type, flags, options, own: dict = None) -> tuple:
    """(size, format, flags, options) VTF карточки: её свои настройки поверх
    общих сборки. Одно правило для всех сборщиков: модели, мода из VPK,
    масок, гирлянд и стилей шапки - иначе шестерёнка карточки работала бы
    только у части из них"""
    eff = effective_settings({'size': size, 'format': format_type,
                              'flags': flags or [], 'options': options or {}}, own)
    size = eff['size']
    size = (size, size) if isinstance(size, int) else tuple(size)
    return size, eff['format'], list(eff['flags'] or []), dict(eff['options'] or {})


def override_badge(override: dict, global_settings: dict = None) -> str:
    """
    Короткая подпись бейджа для карточки с оверрайдом, напр. '1024 · DXT5'.
    Показывает РАЗРЕШЕНИЕ и ФОРМАТ из эффективных настроек. Пусто, если
    оверрайда нет
    """
    if not override:
        return ''
    eff = effective_settings(global_settings or {}, override)
    size = eff.get('size')
    parts = []
    if isinstance(size, (tuple, list)) and len(size) == 2:
        parts.append(str(size[0]))
    fmt = eff.get('format')
    if fmt:
        parts.append(str(fmt))
    return ' · '.join(parts)
