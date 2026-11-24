"""
Где в VPK лежит текстура материала для 3D-превью

Вынесено из Preview3DWorker: чистые функции над открытыми архивами (`paks` -
список pak с доступом `pak[path].read()`), путями `$cdmaterials` и разобранным
QC (QcModel). Отдают байты VTF и имена материалов, картинки на диск пишет и
сигналы шлёт поток

Главное правило: текстуру берём по `$cdmaterials` из QC показываемой модели.
У части оружия в игре две версии (c_items и workshop), и угадывание по
стандартным путям подсовывало текстуру чужой развёртки
"""

from typing import Iterator, Optional

from src.services import qc_skin_parser, texture_guess, vmt_tint
from src.services.game_vpk_reader import GameVpkReader
from src.services.material_resolver import MaterialResolver
from src.shared.logging_config import get_logger
from src.shared.skin_rows import blu_twin, find_name
from src.data.tf2_classes import PROBE_TOKENS
from src.shared.game_paths import game_path

logger = get_logger(__name__)


def read_first(pak, paths: list) -> tuple:
    """Первый существующий путь в архиве -> (байты, путь) или (None, None)"""
    for path in paths:
        try:
            return pak[path].read(), path
        except KeyError:
            continue
    return None, None


# VTF материала из SMD

def player_folder(mode: str, weapon_key: str) -> Optional[str]:
    """Папка materials/models/player/{папка}/ для рук и тел персонажей"""
    import os

    from src.data.item_kinds import kind_of
    from src.data.player_characters import PLAYER_CHARACTERS
    from src.data.player_hands import HAND_MODES
    kind = kind_of(mode)
    if kind.is_hands:
        textures_list = HAND_MODES.get(mode, {}).get("textures", [])
        if textures_list:
            return textures_list[0][0]
    elif kind.is_character:
        # Нельзя просто брать стем MDL - у Heavy MDL = "heavy.mdl",
        # но папка текстур = "hvyweapon"
        return PLAYER_CHARACTERS.get(mode, {}).get(
            "folder",
            os.path.splitext(os.path.basename(weapon_key))[0]
        )
    return None


def guesses(mat_name: str, arm_folder: Optional[str]) -> list:
    """Догадки для материала без VMT: папка персонажа, затем папки оружия"""
    return (texture_guess.player_paths(arm_folder, mat_name)
            + texture_guess.weapon_paths(mat_name))


def _resolver(paks: list) -> MaterialResolver:
    return MaterialResolver(GameVpkReader.over(paks), "", apply_tint=False)


def material_vtf(paks: list, mat_name: str, arm_folder: Optional[str],
                 cdmaterials: list) -> Optional[bytes]:
    """VTF материала той же цепочкой, что у сборки (MaterialResolver.find_vtf)"""
    found = _resolver(paks).find_vtf(
        mat_name, cdmaterials or [], guesses(mat_name, arm_folder))
    return found.data if found else None


def eye_textures(reader, out_dir: str, mat_names: list, found: dict,
                 cdmaterials: list) -> dict:
    """{глаз: PNG радужки} для материалов, которым не нашлось $basetexture

    Игра рисует глаз шейдером EyeRefract: $basetexture у него нет, картинка -
    радужка $iris. Её и показываем, и меняет сборка тоже её
    (texture_build.game_source.write_eye_vmt). Без своей картинки в сборку
    глаза не идут (BuildEditor._misc_to_ask): «скопировать главную» на
    радужку не имеет смысла
    """
    left = [m for m in mat_names if m not in found]
    if not left:
        return {}
    resolver = MaterialResolver(reader, out_dir, eyes=True)
    out = {}
    for mat in left:
        res = resolver.resolve(mat, cdmaterials, out_name=f"eye_{mat.lower()}")
        if res.ok and not res.basetexture:
            out[mat] = res.png_path
    return out


# RED: одна текстура оружия

def weapon_vtf_search(weapon_key: str) -> list:
    """Пути главной текстуры оружия: нестандартные первыми, затем стандартные"""
    from src.data.weapon_quirks import WEAPON_TEXTURE_PATHS
    return WEAPON_TEXTURE_PATHS.get(weapon_key, []) + [
        f"materials/{p}.vtf" for p in texture_guess.weapon_paths(weapon_key)]


def weapon_blu_vtf_search(weapon_key: str) -> list:
    """Пути BLU-текстуры оружия по суффиксу _blue"""
    return [p[:-len(".vtf")] + "_blue.vtf" for p in weapon_vtf_search(weapon_key)]


def red_vtf_via_qc(paks: list, model, weapon_key: str,
                   mat_names: Optional[list] = None) -> tuple:
    """
    RED (skin 0) текстура через QC $cdmaterials -> (байты, имя материала)
    или (None, None). Имя - чтобы краску брать из VMT ЭТОГО же материала

    Читает первую строку $texturegroup (или weapon_key, если группы нет).
    ``mat_names`` - материалы геометрии в кадре: их имена ищем ПЕРВЫМИ.
    У Звона смерти показывается вьюмодель с руками, из которой оставлены
    одни часы, а первая колонка строки - `spy_hands_red`: без этого
    карточка часов показывала руки шпиона
    """
    if model is None or not paks:
        return None, None
    cdmaterials = model.cdmaterials
    if not cdmaterials:
        return None, None

    rows = model.layout.all_rows
    red_tex_names = [t for t in rows[0] if t] if rows else [weapon_key]
    shown = {m.lower() for m in (mat_names or [])}
    if shown:
        red_tex_names = ([t for t in red_tex_names if t.lower() in shown]
                         + [t for t in red_tex_names if t.lower() not in shown])

    logger.debug(
        f"[3D] RED via QC: cdmaterials={cdmaterials}, "
        f"red_tex_names={red_tex_names}"
    )

    resolver = _resolver(paks)
    for tex_name in red_tex_names:
        found = resolver.find_vtf(tex_name, cdmaterials)
        if found:
            logger.info(f"[3D] RED texture via QC: {tex_name} -> {found.path}")
            return found.data, tex_name
    return None, None


def tint_from_vmt_paths(paks: list, vmt_search: list):
    """Краска из первого найденного VMT по списку путей; None - нет"""
    for pak in paks or []:
        for path in vmt_search:
            try:
                return vmt_tint.preview_tint(
                    pak[path].read().decode("utf-8", "replace"))
            except KeyError:
                continue
            except Exception:
                return None
    return None


# BLU через QC skinfamilies

def own_blu_names(model, mat_names: Optional[list]) -> Optional[list]:
    """Синие имена ТОЛЬКО тех столбцов, что принадлежат материалам модели

    Команда в Source меняет материалы поколоночно, поэтому синюю пару надо
    брать из столбца СВОЕГО материала. Пробегать всю строку нельзя: в ней
    стоят и чужие столбцы (у вьюмодели часов рядом с самими часами лежат
    руки шпиона), и общие для команд - и первый же попавшийся `*_blue`
    уезжал предмету на текстуру

    Returns:
        Список синих имён, пустой список - свои столбцы командными не
        оказались (BLU у предмета нет); None - сопоставить не удалось,
        решать вызывающему
    """
    by_lower = {k.lower(): v for k, v in (model.team_map or {}).items()}
    if not by_lower or not mat_names:
        return None
    names: list = []
    matched = False
    for mat in mat_names:
        ml = (mat or "").lower()
        if not ml:
            continue
        blu = team_partner(by_lower, ml)
        if blu is None:
            continue
        matched = True
        if not qc_skin_parser.is_shared_column(ml, blu) and blu not in names:
            names.append(blu)
    return names if matched else None


def team_partner(by_lower: dict, mat_lower: str) -> Optional[str]:
    """Синяя пара материала по карте «RED в нижнем регистре -> BLU»

    Имена материалов SMD и $texturegroup иногда расходятся префиксом пути -
    тогда сверяем по хвосту
    """
    keys = list(by_lower)
    idx = find_name(keys, mat_lower)
    return by_lower[keys[idx]] if idx >= 0 else None


def blu_tex_names(model, mat_names: Optional[list], weapon_key: str) -> list:
    """Синие текстуры модели для одиночного BLU; пусто - BLU у предмета нет

    ``mat_names`` - материалы, которые реально показаны в превью. Строка
    $texturegroup описывает ВСЮ модель, а показываем мы иногда лишь её часть
    (Dead Ringer рисуется вьюмоделью, где рядом с часами лежат руки шпиона)
    """
    layout = model.layout
    if not layout.second_row:
        logger.debug("[3D] _extract_blu_via_qc: второго скина в QC нет → нет BLU варианта")
        return []

    # Переключатель RED/BLU показываем только для настоящей команды
    # (единый авторитет selector_spec.team - тот же, что у сборки), а не для
    # стилей вроде bloody/clean
    if not qc_skin_parser.selector_spec(layout).team:
        logger.info(
            f"[3D] второй скин не является BLU-командой: {layout.second_row} "
            f"- стиль или вариант, переключатель команд не нужен"
        )
        return []

    own = own_blu_names(model, mat_names)
    if own is None:
        return layout.second_row      # сопоставить не с чем - строка как есть
    if not own:
        logger.info(
            f"[3D] {weapon_key}: столбцы модели в $texturegroup командными "
            f"не являются - BLU у предмета нет (строка {layout.second_row})"
        )
    return own


def blu_vtf(paks: list, cdmaterials: list, tex_name: str) -> tuple:
    """VTF синей текстуры -> (байты | None, вид из VMT | None)

    Вид - (basetexture, краска) из VMT: синий материал может отличаться от
    красного только краской
    """
    resolver = _resolver(paks)
    info = resolver.describe(tex_name, cdmaterials or [])
    found = resolver.find_vtf(tex_name, cdmaterials or [])
    look = (info.basetexture, info.tint) if info.vmt_path else None
    return (found.data if found else None), look


def blu_multi_sources(paks: list, model, mat_names: list,
                      arm_folder: Optional[str]) -> Iterator[tuple]:
    """
    BLU-пара каждого материала по QC skinfamilies: (материал, BLU-имя, VTF | None)

    Материал ищется в строке 0 (RED) - по имени, затем по хвосту, - синяя пара
    берётся из того же столбца строки 1. Материалы без пары пропускаются.
    Генератор: при сбое на середине вызывающий сохраняет уже найденное.
    Нужна вторая строка (у модели без неё BLU нет - проверяет вызывающий)
    """
    red_family = [t.lower() for t in model.layout.base_rows[0]]
    blu_family = model.layout.second_row
    for mat_name in mat_names:
        idx = find_name(red_family, mat_name)
        if idx < 0 or idx >= len(blu_family):
            logger.debug(f"[3D] BLU multi: mat '{mat_name}' не найден в RED family")
            continue
        blu_tex_name = blu_family[idx]
        yield mat_name, blu_tex_name, _blu_multi_vtf(
            paks, model.cdmaterials, blu_tex_name, arm_folder)


def _blu_multi_vtf(paks: list, cdmaterials: list, blu_tex_name: str,
                   arm_folder: Optional[str]) -> Optional[bytes]:
    found = _resolver(paks).find_vtf(
        blu_tex_name, cdmaterials or [], guesses(blu_tex_name, arm_folder))
    return found.data if found else None


# Вариант (Australium/Gold/Festive)

def variant_name(model) -> Optional[str]:
    """
    Текстура варианта оружия (Australium/Gold/Festive) по QC или None

    Строку выбирает qc_skin_parser.pick_preview_variant (приоритет у
    настоящего австралиума), текстура - столбец 0 этой строки. VPK здесь не
    нужны: у большинства оружий варианта нет, и открывать архивы зря незачем
    """
    if model is None or not model.cdmaterials:
        return None
    variant_family = qc_skin_parser.pick_preview_variant(model.layout)
    if not variant_family:
        return None
    variant_tex = variant_family[0].lower()
    logger.info(f"[3D] Обнаружен вариант оружия: {variant_tex}")
    return variant_tex


def variant_blu_name(model, variant_tex: Optional[str]) -> Optional[str]:
    """Синее золото или None: у Посла в скине 3 свой `c_ambassador_blue_gold`,
    у клеймора синяя строка та же, что красная. Правило синей строки стиля -
    skin_rows.blu_twin (австралий в игре - стиль со скинами 2 и 3)"""
    rows = list(getattr(getattr(model, 'layout', None), 'all_rows', None) or [])
    low = (variant_tex or '').lower()
    red = next((i for i, row in enumerate(rows) if row and row[0].lower() == low), -1)
    blue = blu_twin(rows, red) if red > 0 else 0
    return rows[blue][0].lower() if blue else None


# Шапка без QC и доп. текстуры по фиксированному пути


_WORKSHOP_SWAPS = [
    ("materials/models/player/items",
     "materials/models/workshop_partner/player/items"),
    ("materials/models/player/items",
     "materials/models/workshop/player/items"),
    ("materials/models/workshop_partner/player/items",
     "materials/models/player/items"),
    ("materials/models/workshop/player/items",
     "materials/models/player/items"),
]


def hat_vtf_paths(weapon_key: str) -> list:
    """Угаданные пути VTF шапки по имени MDL (hat_heavy.mdl -> hat_heavy.vtf)

    `%s` в пути раскрывается во все классы, каждый путь пробуется ещё и в
    папках workshop/workshop_partner
    """
    mdl = game_path(weapon_key)
    if "%s" in mdl:
        mdl_candidates = []
        # Подрывник в путях - `demo` (tf2_classes)
        for cls in PROBE_TOKENS:
            try:
                v = mdl % cls
            except (TypeError, ValueError):
                v = mdl.replace("%s", cls)
            if v not in mdl_candidates:
                mdl_candidates.append(v)
    else:
        mdl_candidates = [mdl]

    vtf_paths: list = []
    for mdl_c in mdl_candidates:
        base_no_ext = mdl_c[:-4] if mdl_c.endswith(".mdl") else mdl_c
        mat_base = "materials/" + base_no_ext
        v0 = mat_base + ".vtf"
        if v0 not in vtf_paths:
            vtf_paths.append(v0)
        for src, dst in _WORKSHOP_SWAPS:
            if src in mat_base:
                v = mat_base.replace(src, dst) + ".vtf"
                if v not in vtf_paths:
                    vtf_paths.append(v)
    return vtf_paths


def fixed_extra_vtf(paks: list, ex: dict) -> Optional[bytes]:
    """VTF доп. текстуры из WEAPON_EXTRA_TEXTURES

    Прямой путь, затем где картинка лежит в игре (мод кладёт её в свою папку
    обхода sv_pure), затем через VMT -> $basetexture (часто VTF лежит не там,
    куда смотрит HUD)
    """
    data = None
    for path in (ex["vpk"], ex.get("game")):
        for pak in paks:
            try:
                data = pak[path].read() if path else None
                break
            except KeyError:
                continue
        if data:
            return data
    if not ex.get("vmt"):
        return data
    for pak in paks:
        try:
            vmt_raw = pak[ex["vmt"]].read()
        except KeyError:
            continue
        base = GameVpkReader.parse_basetexture(
            vmt_raw.decode("utf-8", errors="replace"))
        if base:
            for pak2 in paks:
                data = GameVpkReader.find_vtf_in_pak(pak2, base)
                if data:
                    break
        if data:
            break
    return data


# Материалы $texturegroup вне геометрии

def texturegroup_extras(qc_path: str, mat_names: list) -> list:
    """
    Материалы из QC $texturegroup (колонки 1+), которых НЕТ среди материалов
    геометрии - напр. smiley у гранатомёта демомена. Сборка их предлагает,
    поэтому превью показывает их карточками (тот же блэклист)

    Материалы строк-стилей сюда НЕ попадают: строка стиля выровнена по
    колонкам со строкой 0, поэтому её материал - ЗАМЕНА базового (см.
    style_pairs)
    """
    from src.data.material_filter import is_editable_material, is_user_blacklisted
    from src.services.model_build_service import ModelBuildService
    tg = ModelBuildService.extract_texturegroup_structure(qc_path)
    extras = tg.get('extra_materials', []) or []
    known = {m.lower() for m in mat_names}
    return [m for m in extras
            if m.lower() not in known and is_editable_material(m)
            and not is_user_blacklisted(m)]


def texturegroup_misc(layout, mat_names: list) -> list:
    """Служебные (блэклист) материалы $texturegroup по ВСЕМ строкам, которых
    нет в геометрии - eyeball_invun, *_invun, *_zombie у тела персонажа. Для
    селектора «Прочее», скрытые пользовательским ЧС не попадают"""
    from src.data.material_filter import is_editable_material, is_user_blacklisted
    known = {m.lower() for m in mat_names}
    seen: set = set()
    misc: list = []
    for row in (layout.all_rows or []):
        for m in row:
            ml = (m or '').lower()
            if not ml or ml in known or ml in seen:
                continue
            if not is_editable_material(m) and not is_user_blacklisted(m):
                seen.add(ml)
                misc.append(m)
    return misc


def style_pairs(layout, item_rows=()) -> tuple:
    """
    Пары «базовый материал -> материал стиля» по строкам-стилям QC

    item_rows - строки, которые в игре отдельный предмет (Критокола - строка 2
    модели Бонка, см. item_skin_styles). В QC они безымянные «Skin N», и
    стилем их делает только items_game. Строка-копия более ранней не стиль,
    как в SkinDetectWorker._with_item_styles

    Returns:
        ({индекс скина: {базовый: материал стиля}}, [материалы стилей по порядку]).
        Одинаковый с базой материал стиль наследует - пары у него нет;
        служебные и скрытые не редактируются вовсе
    """
    from src.data.material_filter import is_editable_material, is_user_blacklisted
    rows = layout.all_rows or []
    if not rows:
        return {}, []
    base_row = rows[0]
    wanted: dict = {}
    names: list = []
    styles = [idx for _label, idx in qc_skin_parser.selector_spec(layout).styles]
    styles += [idx for idx in item_rows
               if 0 < idx < len(rows) and idx not in styles and rows[idx] not in rows[:idx]]
    # Синяя строка стиля (огонь Горящих рукавиц) - со своей текстурой
    styles += [twin for twin in (blu_twin(rows, idx) for idx in list(styles))
               if twin and twin not in styles]
    for idx in styles:
        if not 0 <= idx < len(rows):
            continue
        pairs: dict = {}
        for col, base_mat in enumerate(base_row):
            if col >= len(rows[idx]):
                break
            variant = rows[idx][col]
            if (not variant or not base_mat
                    or variant.strip().lower() == base_mat.strip().lower()
                    or not is_editable_material(variant)
                    or is_user_blacklisted(variant)):
                continue
            pairs[base_mat] = variant
            if variant not in names:
                names.append(variant)
        if pairs:
            wanted[idx] = pairs
    return wanted, names
