"""
Карточки чужого мода из VPK: из каких файлов, как выглядят, к чему относятся

Карточка мода названа по его VTF (так их спрашивает сборка мода), а меши
модели - по материалам. Связь между ними та же, что в игре: материал ->
его VMT -> `$basetexture`. Отсюда же командные пары (столбцы $texturegroup)
и карточки только показанной модели в сборнике
"""

from __future__ import annotations

import os
import re
from typing import Callable, Dict, List, Optional, Tuple

from src.services import game_texture_index, vpk_mod_models
from src.services.mod_textures import is_base_vtf, texture_key
from src.shared.logging_config import get_logger
from src.shared.team_names import is_blue

logger = get_logger(__name__)


def card_png(vtf_data: bytes, key: str, preview_dir: str) -> Optional[str]:
    """Первый кадр VTF в PNG превью карточки"""
    from src.services import vtf_preview_service as vps

    safe = re.sub(r'[^A-Za-z0-9_.-]', '_', key)
    return vps.vtf_bytes_to_png(vtf_data, os.path.join(preview_dir, f"_card_{safe}.png"),
                                preview_dir)


def frames(vtf_data: bytes, key: str, vmt_text: str,
           preview_dir: str) -> Optional[Tuple[List[str], float]]:
    """
    Кадры анимированной текстуры карточки: ([PNG], fps) или None

    Анимирована она, только если кадров больше одного И материал крутит их
    прокси AnimatedTexture: без прокси игра рисует первый кадр, и превью
    мигало бы там, где в игре всё стоит
    """
    from src.services import vtf_preview_service as vps

    if vtf_frame_count(vtf_data) < 2:
        return None
    fps = vps.parse_animated_framerate(vmt_text)
    if not fps:
        return None
    from src.services import vmt_tint

    safe = re.sub(r'[^A-Za-z0-9_.-]', '_', key)
    paths = vps.vtf_bytes_to_frame_pngs(vtf_data, preview_dir, f"_card_{safe}_frame")
    if len(paths) < 2:
        return None
    # Краска - как у неподвижной картинки, иначе на ходу кадры теряли бы
    # цвет и показывали маску краски дырами
    spec = vmt_tint.preview_tint(vmt_text)
    for path in paths:
        vmt_tint.apply_to_png(path, spec)
    return paths, float(fps)


def vtf_frame_count(vtf_data: bytes) -> int:
    """Число кадров VTF из заголовка (uint16 по смещению 24): до разбора
    всех кадров, который стоит секунды"""
    if len(vtf_data) < 26 or vtf_data[:4] != b"VTF\0":
        return 1
    return int.from_bytes(vtf_data[24:26], "little")


def build(pak, vtf_files: List[str], vmt_files: List[str], vmt_texts: Dict[str, str],
          refs, preview_dir: str, game_vtf: Callable[[str], Optional[bytes]]) -> list:
    """Карточки ВСЕХ основных VTF мода

    Служебные VTF (lightwarp/bump/normal/…) отброшены через is_base_vtf. Имя
    карточки - стебель VTF, при совпадении стеблей добавляется папка. Превью -
    первый кадр. `game_vtf(текстура)` - байты игровой текстуры для карт,
    которые смотрят в игру
    """
    from src.services import vmt_parse

    # VMT для текстуры: тот, чей $basetexture на неё смотрит (так её
    # находит игра), иначе - по совпадению стебля
    vmt_by_stem: Dict[str, str] = {}
    vmt_by_base: Dict[str, str] = {}
    for vmt_rel in vmt_files:
        stem = os.path.splitext(os.path.basename(vmt_rel))[0].lower()
        vmt_by_stem.setdefault(stem, vmt_rel)
        base_tex = vmt_parse.parse(vmt_texts.get(vmt_rel, '')).path('$basetexture')
        if base_tex:
            vmt_by_base.setdefault(texture_key(base_tex), vmt_rel)
    vtf_by_key = {texture_key(v): v for v in vtf_files}

    base = sorted(v for v in vtf_files if is_base_vtf(v, refs))
    counts: Dict[str, int] = {}
    for v in base:
        s = os.path.splitext(os.path.basename(v))[0]
        counts[s] = counts.get(s, 0) + 1

    cards = []
    used: set = set()
    for vtf_rel in base:
        stem = os.path.splitext(os.path.basename(vtf_rel))[0]
        folder = os.path.basename(os.path.dirname(vtf_rel))
        name = stem if counts.get(stem, 0) <= 1 else f"{stem} [{folder}]"
        while name in used:
            name += "_"
        used.add(name)

        preview_png = None
        try:
            preview_png = card_png(pak[vtf_rel].read(), name, preview_dir)
        except Exception as exc:                             # noqa: BLE001
            logger.debug(f"VPK мод: превью VTF не удалось ({vtf_rel}): {exc}")

        vmt_rel = vmt_by_base.get(texture_key(vtf_rel)) or vmt_by_stem.get(stem.lower())
        cards.append({
            'name': name,
            'display_name': name,
            'is_blue': is_blue(stem),
            'vtf_path': vtf_rel,
            'preview_png': preview_png,
            'vmt_path': vmt_rel,
            'maps': _maps(pak, name, vmt_texts.get(vmt_rel, ''), vtf_by_key, preview_dir,
                          game_vtf),
        })

    # RED-материалы первыми, затем BLU (как в обычной раскладке карточек)
    return [c for c in cards if not c['is_blue']] + [c for c in cards if c['is_blue']]


def _maps(pak, card: str, vmt_text: str, vtf_by_key: dict, preview_dir: str,
          game_vtf) -> dict:
    """Карты материала, что уже стоят в VMT мода, - с превью их текстуры
    (диалог карт показывает их отмеченными)"""
    from src.data.material_maps import detect_maps

    maps = detect_maps(vmt_text)
    for map_id, entry in maps.items():
        texture = entry.get('texture')
        if not texture:
            continue
        vtf_rel = vtf_by_key.get(texture_key(texture))
        try:
            # Своя текстура мода, иначе игровая (lightwarp модов часто
            # смотрит на полоску самой игры)
            data = pak[vtf_rel].read() if vtf_rel else game_vtf(texture)
            if data:
                entry['preview'] = card_png(data, f"{card}__{map_id}", preview_dir)
        except Exception as exc:                             # noqa: BLE001
            logger.debug(f"VPK мод: превью карты {map_id} не вышло ({texture}): {exc}")
    return maps


def game_vmt_text(misc_vpk: str, vmt: str) -> str:
    """Текст VMT игры по пути в tf2_misc_dir.vpk или пусто"""
    if not (vmt and misc_vpk):
        return ''
    from src.services.vpk_cache import open_vpk_cached
    try:
        return open_vpk_cached(misc_vpk)[vmt].read().decode('utf-8', 'replace')
    except Exception:                                        # noqa: BLE001
        return ''


def tint(cards: list, vmt_texts: Dict[str, str], misc_vpk: str) -> None:
    """Краска - как в игре: у шапки альфа текстуры - маска краски, а не
    прозрачность (`$blendtintbybasealpha`). Материал - мода, а у мода из
    одних текстур - игровой. Картинка с маской остаётся рядом: по ней
    превью перекрашивает шапку любой банкой (vmt_tint.painted)"""
    from src.services import vmt_tint

    table: list = []
    for card in cards:
        text = _card_vmt(card, vmt_texts, misc_vpk, table)
        if card.get('preview_png'):
            vmt_tint.apply_to_png(card['preview_png'], vmt_tint.preview_tint(text))


def animate(cards: list, pak, vmt_texts: Dict[str, str], misc_vpk: str,
            preview_dir: str) -> None:
    """Кадры анимированных карточек (`frames`, `fps` в самой карточке).
    Материал - тот же, что у краски: у мода из одних текстур VMT игровой,
    и прокси AnimatedTexture живёт в нём"""
    table: list = []
    for card in cards:
        try:
            data = pak[card['vtf_path']].read()
        except Exception:                                    # noqa: BLE001
            continue
        if vtf_frame_count(data) < 2:
            continue
        moving = frames(data, card['name'], _card_vmt(card, vmt_texts, misc_vpk, table),
                        preview_dir)
        if moving:
            card['frames'], card['fps'] = moving


def _card_vmt(card: dict, vmt_texts: Dict[str, str], misc_vpk: str, table: list) -> str:
    """Текст VMT карточки: мода, иначе игровой по пути её текстуры. `table` -
    указатель текстур игры, читается один раз на список"""
    text = vmt_texts.get(card.get('vmt_path') or '', '')
    if not text and misc_vpk:
        if not table:
            table.append(game_texture_index.load(misc_vpk))
        text = game_vmt_text(misc_vpk, game_texture_index.vmt_for(card['vtf_path'], table[0]))
    return text


def _vmt_by_path(rel: str, vmt_texts: Dict[str, str], misc_vpk: str) -> str:
    """Текст VMT материала по пути без materials/ и .vmt: сначала мода (в том
    числе из папки-обхода), иначе игры - у мода из одних текстур VMT игровой"""
    want = texture_key(rel)
    for vmt, text in vmt_texts.items():
        key = texture_key(vmt[:-4] if vmt.lower().endswith('.vmt') else vmt)
        if key == want or key.endswith('/' + want):
            return text
    return game_vmt_text(misc_vpk, f'materials/{want}.vmt')


def links(decomp_dir: str, model_materials: List[str], cards: list,
          vmt_texts: Dict[str, str], misc_vpk: str) -> Tuple[dict, dict]:
    """({материал модели: карточка}, {красная карточка: синяя})

    Пары команд - столбцы $texturegroup модели (QcModel.team_map): у оружия
    строка 0 - RED, 1 - BLU. Синяя карточка - синяя сторона красной, а не
    отдельная: огоньки гирлянды RED и BLU стояли в ряду рядом
    """
    from src.services import qc_skin_parser

    model = qc_skin_parser.load_model(decomp_dir)
    team = model.team_map if model else {}
    mats = sorted({*model_materials, *team, *team.values()})
    found = vpk_mod_models.mesh_links(
        mats, list(model.cdmaterials) if model else [],
        lambda rel: _vmt_by_path(rel, vmt_texts, misc_vpk),
        {c['name']: texture_key(c.get('vtf_path') or '') for c in cards})
    meshes = {m: found[m] for m in model_materials if m in found}
    # Синий материал, который сам стоит на красном меше (общий столбец,
    # как у hwn2022_alcoholic_automaton), - своя карточка, а не синяя сторона:
    # спрятанный, он пропадал бы из правки за RED
    shown = {m.lower() for m in model_materials}
    blue = {found[r]: found[b] for r, b in team.items()
            if r in found and b in found and found[r] != found[b]
            and b.lower() not in shown}
    return meshes, blue


def game_meshes(decomp_dir: str, model_materials: List[str], linked: Dict[str, str],
                vmt_texts: Dict[str, str], misc_vpk: str,
                vtf_data: Callable[[str], Optional[bytes]],
                preview_dir: str) -> Dict[str, dict]:
    """
    {меш: {png, frames?, fps?}} - меши без карточки мода

    Мод ссылается на игровые текстуры, если не менял их (так собирает и это
    приложение): огоньки вшитой гирлянды берут игровой VTF. Карточки бывают
    только у файлов мода, и такие меши оставались под главной текстурой -
    огоньки в цвет приклада и без мигания. Текстура находится как в игре:
    материал -> VMT (мода, иначе игры) -> `$basetexture` -> VTF
    (`vtf_data(путь)`: из мода, иначе из игры). В карточки не идёт: менять
    игровую текстуру значило бы менять её у всех предметов
    """
    from src.services import qc_skin_parser, vmt_parse, vmt_tint

    model = qc_skin_parser.load_model(decomp_dir) if decomp_dir else None
    cds = list(model.cdmaterials) if model else []
    out: Dict[str, dict] = {}
    for mat in model_materials:
        if mat in linked:
            continue
        text = vpk_mod_models.material_vmt(
            mat, cds, lambda rel: _vmt_by_path(rel, vmt_texts, misc_vpk))
        base = vmt_parse.parse(text).path('$basetexture') if text else ''
        data = vtf_data(base) if base else None
        png = card_png(data, f"scene_{mat}", preview_dir) if data else None
        if not png:
            continue
        vmt_tint.apply_to_png(png, vmt_tint.preview_tint(text))
        moving = frames(data, f"scene_{mat}", text, preview_dir)
        out[mat] = {'png': png, **({'frames': moving[0], 'fps': moving[1]} if moving else {})}
    return out


def own(decomp_dir: Optional[str], model_materials: List[str], cards: list,
        vmt_texts: Dict[str, str]) -> list:
    """Карточки только показанной модели: её материалы, стили из QC и
    `$cdmaterials` ведут к VMT, а те - к текстурам. Не разобралось - все
    карточки: лишние лучше пустого альбома"""
    from src.services import qc_skin_parser

    model = qc_skin_parser.load_model(decomp_dir) if decomp_dir else None
    names = set(model_materials)
    if model is not None:
        names.update(n for row in model.layout.all_rows for n in row)
    key = {c['name']: texture_key(c.get('vtf_path') or '') for c in cards}
    mine = vpk_mod_models.textures_of(
        sorted(names), list(model.cdmaterials) if model else [], vmt_texts,
        list(key.values()))
    return [c for c in cards if key[c['name']] in mine] or cards
