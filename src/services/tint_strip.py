"""
Ответ «Без покраски»: снять краску игры с материалов, у текстуры которых нет
своей маски

Игра красит материал с `$blendtintbybasealpha` там, где альфа текстуры белая.
Своя картинка без альфы становится текстурой с белой альфой целиком, и
предмет в игре красится весь. Краску снимаем из VMT, а картинку не трогаем:
пустая альфа в ней прятала бы краску, но делала текстуру тяжелее (DXT1
становится DXT5) и ломалась бы первой же картинкой с альфой

Решаем по самому моду, а не по списку карточек: так не нужно сопоставлять
имена карточек с материалами (синие пары, одноматериальные модели), и
материал со своей маской краску сохраняет
"""

from pathlib import Path
from typing import Iterable, List, Optional

from src.shared.logging_config import get_logger

logger = get_logger(__name__)

#: Альфа не ниже этого - маски нет (как vmt_tint.lacks_alpha у картинки)
_OPAQUE = 250


def strip_unmasked(root, only: Optional[Iterable] = None) -> List[str]:
    """
    Снимает краску игры с VMT мода, чья текстура лежит в моде и маски не имеет

    Args:
        root: корень мода (в нём папка materials).
        only: VTF, которые можно трогать (мод из VPK: только заменённые в
            этой сборке, файлы автора мода не трогаем). None - все в моде.

    Returns:
        Имена VMT, с которых краска снята
    """
    from src.services import vmt_parse, vmt_tint
    from src.services.game_vpk_reader import texture_path
    from src.services.vmt_service import VMTService

    root = Path(root)
    allowed = None if only is None else {_key(p) for p in only}
    stripped: List[str] = []
    for vmt in sorted(root.rglob("*.vmt")):
        try:
            text = vmt.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if vmt_tint.parse_tint(text) is None:
            continue
        base = texture_path(vmt_parse.parse(text).path("basetexture") or "")
        vtf = root / "materials" / f"{base}.vtf"
        # Текстуры в моде нет - VMT смотрит на игру, там краска игровая и верная
        if not base or not vtf.is_file():
            continue
        if allowed is not None and _key(vtf) not in allowed:
            continue
        if not _opaque(vtf):
            continue
        VMTService.remove_paint_proxies(str(vmt))
        stripped.append(vmt.name)
        logger.info(f"[tint] покраска игры снята: {vmt.name}")
    return stripped


def _key(path) -> str:
    return str(Path(path).resolve()).lower()


def _opaque(vtf: Path) -> bool:
    """Альфа текстуры сплошь белая. Не читается - считаем, что маски нет:
    человек просил снять покраску, и оставить её было бы хуже"""
    from src.services.vtflib_wrapper import VTFLib

    try:
        raw, _w, _h = VTFLib.read_vtf_as_rgba(str(vtf))
    except Exception as exc:                          # noqa: BLE001
        logger.warning(f"[tint] альфа {vtf.name} не читается, краску снимаем: {exc}")
        return True
    return min(raw[3::4], default=255) >= _OPAQUE
