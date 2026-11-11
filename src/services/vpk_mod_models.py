"""
Модели внутри чужого VPK-мода: какие есть, какие показать, где взять игровую

В одном моде бывает несколько моделей (пушка, её гирлянда, руки, снаряд) -
человек выбирает, какую показать. Мод из одних текстур своей модели не несёт:
показывается игровая, которая их рисует (game_texture_index)
"""

from __future__ import annotations

import os
import re
from typing import Dict, List, Optional, Sequence, Tuple

#: Порядок групп в списке выбора
KINDS = ('weapon', 'garland', 'arms', 'player', 'cosmetic', 'projectile',
         'pickup', 'other')


def stem(path: str) -> str:
    return os.path.splitext(os.path.basename(path.replace('\\', '/')))[0].lower()


def kind_of(mdl_path: str) -> str:
    """Что это за модель - по её пути в игре"""
    from src.data.weapons import WEAPON_MDL_PATHS

    path = mdl_path.replace('\\', '/').lower()
    name = stem(path)
    if name.endswith(('_xmas', '_festivizer')):
        return 'garland'
    if name.endswith('_arms') or '/c_arms' in path:
        return 'arms'
    if path.startswith(('models/player/items/', 'models/workshop/player/',
                        'models/workshop_partner/player/')):
        return 'cosmetic'
    if path.startswith('models/player/'):
        return 'player'
    # Раньше таблицы оружия: в ней есть и снаряды с аптечками
    if '/w_models/' in path or 'projectile' in path:
        return 'projectile'
    if path.startswith('models/items/'):
        return 'pickup'
    if name in WEAPON_MDL_PATHS or path.startswith(('models/weapons/',
                                                    'models/workshop/weapons/')):
        return 'weapon'
    return 'other'


def is_stub(mdl_bytes: bytes) -> bool:
    """Пустая модель-заглушка из нашей сборки: гирлянда вшита в оружие, а
    родная заменена невидимым треугольником (decor_bake). Показывать в ней
    нечего, и раньше она открывалась «плоской текстурой» со всеми карточками"""
    from src.services.decor_bake import EMPTY_MATERIAL
    from src.services.mdl_mesh import materials

    try:
        names, _cds = materials(mdl_bytes)
    except Exception:                                        # noqa: BLE001
        return False
    return bool(names) and all(stem(n) == EMPTY_MATERIAL for n in names)


def real_models(pak) -> List[str]:
    """MDL мода без заглушек"""
    out = []
    for p in pak:
        if p.lower().endswith('.mdl'):
            try:
                if is_stub(pak[p].read()):
                    continue
            except Exception:                                # noqa: BLE001
                pass
            out.append(p)
    return out


def list_models(vpk_path: str) -> List[Dict[str, str]]:
    """Модели мода для выбора: [{path, name, kind}] по группам и именам"""
    import vpk as vpklib

    found = real_models(vpklib.open(vpk_path))
    out = [{'path': p, 'name': stem(p), 'kind': kind_of(p)} for p in found]
    out.sort(key=lambda m: (KINDS.index(m['kind']), m['name']))
    return out


#: Что бывает в модах без моделей и текстур. Список целиком подставляется в
#: фразу, и словарь интерфейса его не переведёт - поэтому язык выбирается здесь
_OTHER = {
    'ru': {'particles': 'частицы', 'sounds': 'звуки', 'maps': 'карты',
           'hud': 'интерфейс', 'configs': 'конфиги', 'scripts': 'скрипты',
           'materials': 'материалы без текстур', 'other': 'другие файлы'},
    'en': {'particles': 'particles', 'sounds': 'sounds', 'maps': 'maps',
           'hud': 'HUD', 'configs': 'configs', 'scripts': 'scripts',
           'materials': 'materials without textures', 'other': 'other files'},
}
_NOT_SHOWN = {
    'ru': 'Этот мод здесь не открыть: в нём {} и ни одной модели или текстуры',
    'en': "This mod can't be opened here: it has {} and no models or textures",
}


def _other_kind(path: str) -> str:
    p = path.replace('\\', '/').lower()
    if p.endswith('.pcf'):
        return 'particles'
    if p.startswith('sound/'):
        return 'sounds'
    if p.endswith('.bsp') or p.startswith('maps/'):
        return 'maps'
    if p.startswith('resource/') or p.startswith('scripts/hud'):
        return 'hud'
    if p.startswith('cfg/'):
        return 'configs'
    if p.startswith('scripts/'):
        return 'scripts'
    if p.endswith('.vmt'):
        return 'materials'
    return 'other'


def why_not_shown(files: Sequence[str], lang: str = 'ru') -> str:
    """Почему мод не открыть в окне предмета; пусто - открыть можно

    Окно показывает модель и правит текстуры. Мод из одних частиц или звуков
    раньше падал «непредвиденной ошибкой» с советом про .mdl
    """
    if not files or any(f.lower().endswith(('.mdl', '.vtf')) for f in files):
        return ''
    found = {_other_kind(f) for f in files}
    lang = 'ru' if lang == 'ru' else 'en'
    words = _OTHER[lang]
    return _NOT_SHOWN[lang].format(', '.join(w for k, w in words.items() if k in found))


def weapon_key(path: str) -> Optional[str]:
    """Ключ оружия (c_xxx из таблицы оружия) в пути модели, иначе None.
    Ключ обычно в конце пути, поэтому кандидаты перебираются с конца"""
    from src.data.weapons import WEAPON_MDL_PATHS

    for part in reversed(re.findall(r"(c_[a-z0-9_]+)", (path or '').lower())):
        if part in WEAPON_MDL_PATHS:
            return part
    return None


def target(files: Sequence[str], vmt_texts: Dict[str, str], wanted: str,
           misc_vpk: str) -> Tuple[str, bool]:
    """(модель, которую мод показывает и заменяет, своя ли она)

    Своя - выбранная человеком из моделей мода, иначе само оружие или первая.
    Мод из одних текстур перекрашивает модель игры, которая их рисует
    (game_texture_index); пусто - такой нет. Одно решение и для разбора мода,
    и для страницы, которой надо знать раздел ещё до разбора
    """
    mdls = [f for f in files if f.lower().endswith('.mdl')]
    if mdls:
        key = next((k for k in map(weapon_key, mdls) if k), None)
        return pick(mdls, wanted, key), True
    vtfs = [f for f in files if f.lower().endswith('.vtf')]
    if not (vtfs and misc_vpk):
        return '', False
    from src.services import game_texture_index
    from src.services.mod_textures import is_base_vtf, vmt_references

    refs = vmt_references(vmt_texts.values())
    base = [v for v in vtfs if is_base_vtf(v, refs)]
    return game_texture_index.model_for(vtfs, base, game_texture_index.load(misc_vpk)), False


def pick(mdl_files: Sequence[str], wanted: str, weapon_key: Optional[str]) -> str:
    """Какую модель мода показать

    `wanted` - выбор человека (путь MDL). Пусто или мимо - само оружие (имя
    файла = ключ: рядом может лежать его гирлянда) или первая
    """
    want = (wanted or '').replace('\\', '/').lower()
    for mdl in mdl_files:
        if want and mdl.replace('\\', '/').lower() == want:
            return mdl
    for mdl in mdl_files:
        if weapon_key and stem(mdl) == weapon_key:
            return mdl
    return mdl_files[0]


def textures_of(materials: Sequence[str], cdmaterials: Sequence[str],
                vmt_texts: Dict[str, str], textures: Sequence[str]) -> set:
    """Какие из `textures` (ключи texture_key) рисуют эти материалы модели

    Игра ищет материал как `<$cdmaterials>/<имя>.vmt`, а VMT уже называет
    свои текстуры. Так в огромном моде (сборник пушек) у выбранной модели
    остаются только её карточки. Текстура без VMT, названная как материал, -
    тоже её: так кладут моды, где VMT взят из игры

    Совпадение - по концу пути: собранный мод лежит в папке-обходе
    (materials/console/models/...), а разбор QC эту папку из $cdmaterials
    убирает
    """
    from src.services.mod_textures import texture_key, vmt_references

    # `$cdmaterials` в QC обычно кончается слэшем ("...\\c_gun\\"): склейка
    # через ещё один давала двойной, и ничего не совпадало
    wanted = {texture_key('/'.join(p for p in (cd.replace('\\', '/').strip('/'), m) if p))
              for cd in (*cdmaterials, '') for m in materials}

    def ends(key: str, names) -> bool:
        return any(key == w or key.endswith('/' + w) for w in names)

    texts = [t for rel, t in vmt_texts.items()
             if ends(texture_key(rel[:-4] if rel.lower().endswith('.vmt') else rel), wanted)]
    refs = vmt_references(texts)
    named = refs['base'] | refs['service']
    return {k for k in textures if k in named or ends(k, wanted)}


def _tail_match(a: str, b: str) -> bool:
    """Один путь - конец другого: мод лежит в папке-обходе (console/...)"""
    return a == b or a.endswith('/' + b) or b.endswith('/' + a)


def mesh_links(materials: Sequence[str], cdmaterials: Sequence[str], vmt_text,
               card_keys: Dict[str, str]) -> Dict[str, str]:
    """{материал модели: карточка мода} - так же, как находит игра

    Материал ищется как `<$cdmaterials>/<имя>.vmt` (`vmt_text(путь)` отдаёт
    текст VMT или пусто), его `$basetexture` - файл карточки (`card_keys`:
    {карточка: ключ её VTF}). Раньше карточку с мешем связывало только
    совпадение имён, и у шляпы с текстурой `paper_hat_color` на материале
    `paper_hat` сцены оставались без текстуры мода
    """
    from src.services import vmt_parse
    from src.services.mod_textures import texture_key

    out: Dict[str, str] = {}
    for mat in materials:
        for cd in (*cdmaterials, ''):
            text = vmt_text('/'.join(p for p in (cd.replace('\\', '/').strip('/'), mat) if p))
            if text:
                break
        else:
            continue
        base = vmt_parse.parse(text).path('$basetexture')
        if not base:
            continue
        key = texture_key(base)
        card = next((c for c, k in card_keys.items() if _tail_match(k, key)), None)
        if card:
            out[mat] = card
    return out


def sky_faces(cards: Sequence[dict]) -> Dict[str, str]:
    """{грань: карточка} неба, которое перекрашивает мод; пусто - не небо

    Грань - по концу имени текстуры в materials/skybox/ (`sky_upwardup`,
    `sky_harvest_01_up`). У стоковых небес четыре бока - одна текстура
    `side`. Небес в моде несколько - берётся самое полное
    """
    from src.data.skyboxes import SKY_FACES, SKY_SIDE_FACES

    skies: Dict[str, Dict[str, str]] = {}
    for card in cards:
        path = (card.get('vtf_path') or '').replace('\\', '/').lower()
        if not path.startswith('materials/skybox/') or card.get('is_blue'):
            continue
        name = stem(path)
        for token in ('side', *SKY_FACES):
            if name.endswith(token) and len(name) > len(token):
                faces = skies.setdefault(name[:-len(token)].rstrip('_'), {})
                for face in (SKY_SIDE_FACES if token == 'side' else (token,)):
                    faces.setdefault(face, card['name'])
                break
    if not skies:
        return {}
    # HDR-вариант (`_hdr`) - запасной: обычный видят все
    best = max(skies, key=lambda s: (len(skies[s]), not s.endswith('_hdr')))
    return skies[best]
