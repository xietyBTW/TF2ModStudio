"""
VMT, записанный копией чужого, возвращает свой игровой вид

Сборка пишет VMT многих материалов копией готового VMT мода: синий - копией
красного, материал стиля шапки - копией главного. Так в копию попадают своя
текстура, правки человека, снятая краска, нормаль, анимация. Но с ними
попадает и то, чем у Valve образец отличается от этого материала. В игре 2872
командные пары, и у 1291 команды отличаются краской `$colortint_base`: шапка
синего выходила цвета красных. Реже - свечением, отражениями, бликом, цветом
невидимости шпиона. У стиля - вообще всеми своими параметрами

Правило одно: за основу берётся СВОЙ игровой VMT материала, и на него ложится
разница между игровым VMT образца и тем, что мод записал
(part_materials.overlay_vmt - так же правка части переносится на её синюю
строку). Что мод не трогал, остаётся как у Valve; что трогал - его
"""

from pathlib import Path
from typing import Iterable, List, Optional, Sequence, Tuple

from src.shared.logging_config import get_logger

logger = get_logger(__name__)


def inherit(vmt: Path, template_game: str, own_game: str) -> bool:
    """
    Переписывает VMT мода поверх своего игрового VMT

    Args:
        vmt: VMT мода, записанный копией образца.
        template_game: игровой VMT образца (с чего начиналась копия).
        own_game: игровой VMT самого материала.

    Returns:
        True, если файл изменён
    """
    from src.services import vmt_parse
    from src.services.part_materials import overlay_vmt

    if vmt_parse.fingerprint(vmt_parse.parse(template_game)) == \
            vmt_parse.fingerprint(vmt_parse.parse(own_game)):
        return False     # у Valve они одинаковы - возвращать нечего
    mine = vmt.read_bytes().decode("utf-8", errors="replace")
    out = overlay_vmt(own_game, template_game, mine)
    if out == mine:
        return False
    vmt.write_bytes(out.encode("utf-8"))
    return True


def inherit_pairs(folder, pairs: Iterable[Tuple[str, str]],
                  template_cds: Sequence[str], vpk_paths: Sequence[Optional[str]],
                  own_cds: Optional[Sequence[str]] = None) -> List[str]:
    """
    `inherit` для пар (образец, материал), чей VMT записан в `folder`

    Командные пары модели - (красный, синий) из её $texturegroup, у стиля
    шапки - (главный материал, материал стиля). Игровые VMT ищутся по
    `$cdmaterials` оригинальных моделей: образца - `template_cds`, материала -
    `own_cds` (по умолчанию те же)

    Returns:
        Имена материалов, чей VMT переписан
    """
    from src.services import qc_skin_parser
    from src.services.game_vpk_reader import GameVpkReader

    folder = Path(folder)
    t_cds = qc_skin_parser.resolve_cdmaterials(list(template_cds or ()))
    o_cds = (qc_skin_parser.resolve_cdmaterials(list(own_cds)) if own_cds is not None
             else t_cds)
    reader = GameVpkReader(list(vpk_paths or ()))
    done: List[str] = []
    try:
        for template, name in pairs:
            if not template or not name or template.lower() == name.lower():
                continue
            target = next((p for p in (folder / f"{name.lower()}.vmt", folder / f"{name}.vmt")
                           if p.is_file()), None)
            if target is None:
                continue
            game_t = reader.find_vmt(t_cds, template.lower())
            game_o = reader.find_vmt(o_cds, name.lower())
            if game_t and game_o and inherit(target, game_t[1], game_o[1]):
                done.append(name)
    finally:
        reader.close()
    if done:
        logger.info(f"[look] VMT вернули свой игровой вид: {done}")
    return done
