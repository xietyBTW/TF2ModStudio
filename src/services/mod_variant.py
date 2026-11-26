"""
Австралий у мода из VPK

Есть ли он, решает модель, которую рисует мод: своя (её таблица скинов) или
игровая (у мода из одних текстур). Картинка - золото мода, если оно в нём
есть, иначе игровое. Сборке нужно ещё, куда дописать золото, которого у мода
нет: первая папка $cdmaterials этой модели и игровой VMT золота
"""

from __future__ import annotations

import os
import re
from typing import Dict, List, Optional

from src.services import qc_skin_parser, texture_locator
from src.services.game_vpk_reader import GameVpkReader
from src.shared.constants import strip_bypass_console
from src.shared.logging_config import get_logger

logger = get_logger(__name__)


def _stem(path: str) -> str:
    return os.path.splitext(os.path.basename(path.replace('\\', '/')))[0].lower()


def _mod_card(material: str, cards: List[dict], vmt_texts: Dict[str, str]) -> Optional[dict]:
    """Карточка золота в моде: по VTF с именем материала, иначе по
    $basetexture его VMT (карточки названы по VTF)"""
    by_name = {str(c.get('name', '')).lower(): c for c in cards}
    if material in by_name:
        return by_name[material]
    for rel, text in vmt_texts.items():
        if _stem(rel) == material:
            base = GameVpkReader.parse_basetexture(text)
            if base and _stem(base) in by_name:
                return by_name[_stem(base)]
    return None


def _first_dir(qc_path: str, own_model: bool, resolved: List[str]) -> str:
    """Папка, где модель первым делом ищет материалы. У своей модели мода -
    как записано в её QC (с папкой-обходом), у игровой - путь игры"""
    if own_model:
        try:
            with open(qc_path, encoding='utf-8', errors='replace') as f:
                raw = re.findall(r'\$cdmaterials\s+"([^"]+)"', f.read(), re.IGNORECASE)
        except OSError:
            raw = []
        first = next((r.replace('\\', '/').strip('/') for r in raw if r.strip('\\/')), '')
        if first:
            return first
    return resolved[0] if resolved else ''


def _side(material: str, cards: List[dict], vmt_texts: Dict[str, str],
          reader: GameVpkReader, game_cds: List[str], out_dir: str,
          folder: str) -> Optional[dict]:
    """Одна сторона золота: {card, material, png, in_mod, folder, game_vmt}"""
    card = _mod_card(material, cards, vmt_texts)
    png = card.get('preview_png') if card else None
    found = reader.find_vmt(game_cds, material)
    if not png:
        from src.services.material_resolver import MaterialResolver
        png = MaterialResolver(reader, out_dir).resolve(
            material, game_cds, out_name=f'mod_variant_{material}').png_path
    if not png:
        return None
    return {'card': card['name'] if card else material, 'material': material,
            'png': png, 'in_mod': card is not None, 'folder': folder,
            'game_vmt': found[1] if found else None}


def detect(decomp_dir: str, cards: List[dict], vmt_texts: Dict[str, str],
           textures_vpk: str, misc_vpk: str, out_dir: str,
           own_model: bool = False) -> Optional[dict]:
    """
    {card, material, png, in_mod, folder, game_vmt, blue} или None

    card - под каким именем карточка: имя VTF мода (так его спрашивает
    сборка), иначе имя материала. folder и game_vmt - куда и чем сборка
    дописывает золото, если в моде его нет. blue - синее золото в том же
    виде (у Посла и у мода, сделанного командным), иначе None: оно - синяя
    сторона карточки австралия, а не своя карточка
    """
    model = qc_skin_parser.load_model(decomp_dir)
    material = texture_locator.variant_name(model)
    if not material:
        return None
    cds = [c for c in model.cdmaterials if c is not None]
    # Своя модель смотрит в папку-обход, а золото игры лежит по её пути
    game_cds = list(dict.fromkeys([strip_bypass_console(c) for c in cds] + cds))
    folder = _first_dir(model.qc_path, own_model, cds)
    blue_name = texture_locator.variant_blu_name(model, material)
    with GameVpkReader([textures_vpk, misc_vpk]) as reader:
        red = _side(material, cards, vmt_texts, reader, game_cds, out_dir, folder)
        blue = (_side(blue_name, cards, vmt_texts, reader, game_cds, out_dir, folder)
                if red and blue_name and blue_name != material else None)
    if not red:
        logger.info(f"VPK мод: вариант {material} без картинки - не показываем")
        return None
    logger.info(f"VPK мод: вариант {material} ({'в моде' if red['in_mod'] else 'игровой'}), "
                f"синий {blue['card'] if blue else '-'}")
    return {**red, 'blue': blue, 'meshes': _replaced(model.layout.all_rows, material)}


def _replaced(rows: List[List[str]], material: str) -> List[str]:
    """Материалы обычной строки, которые строка австралия заменяет: их меши
    игра и рисует золотом"""
    row = next((r for r in rows if r and r[0].lower() == material), None)
    base = rows[0] if rows else []
    return [b.lower() for b, v in zip(base, row or []) if b.lower() != v.lower()]


# Сборка: золото, которого в моде нет

_BASETEXTURE = re.compile(r'("?\$basetexture"?\s+)"?[^"\r\n]*"?', re.IGNORECASE)


def missing_texture(vpkroot, info: dict, textures: List[dict]) -> Optional[dict]:
    """
    Текстура золота для сборщика мода, если своего VTF у мода нет

    VMT - свой у мода (бывает, что смотрит в игру), иначе игровой, в папке,
    где модель ищет материалы первым делом. Пишется он только вместе с
    картинкой человека (write_vmt): без неё игра и так берёт своё золото
    """
    from pathlib import Path

    names = {str(t.get('name', '')).lower() for t in textures}
    material = info.get('material') or ''
    if not material or info.get('in_mod') or str(info.get('card', '')).lower() in names:
        return None
    root = Path(vpkroot)
    own = next((p for p in root.rglob('*.vmt') if p.stem.lower() == material), None)
    if own is not None:
        vmt, text = own, own.read_text(encoding='utf-8', errors='replace')
    elif info.get('game_vmt'):
        vmt = root / 'materials' / (info.get('folder') or '') / f'{material}.vmt'
        text = info['game_vmt']
    else:
        return None
    folder = vmt.parent.relative_to(root / 'materials').as_posix()
    base = f'{folder}/{material}' if folder != '.' else material
    if _BASETEXTURE.search(text):
        text = _BASETEXTURE.sub(lambda m: f'{m.group(1)}"{base}"', text, count=1)
    else:
        text = text.replace('{', f'{{\n\t"$basetexture" "{base}"', 1)
    return {'name': info.get('card') or material, 'vtf_name': material,
            'vmt_dir': str(vmt.parent), 'vtf_path': str(vmt.parent / f'{material}.vtf'),
            'vmt_path': str(vmt), 'is_blue': False, 'vmt_text': text}


def write_vmt(tex: dict) -> None:
    """VMT золота на место: игровой с $basetexture на VTF мода"""
    from pathlib import Path

    path = Path(tex['vmt_path'])
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(tex['vmt_text'], encoding='utf-8')
