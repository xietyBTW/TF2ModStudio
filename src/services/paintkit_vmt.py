"""
Материал War Paint: то, чем часть раскрасок блестит в игре

Обычный War Paint меняет на пушке только картинку. Но у 38 из 250 в описании
пушки стоит свой материал (`material_override` в proto_defs): игра надевает
его вместо стокового, и уже на него кладёт картинку. Это глянец `macaw`
(Party Phantoms, Macaw Masked, Raving Dead... - острый блик цвета краски,
слабое отражение, подсветка по краю), его копия `_sheen` у Leopard Printed и
Tiger Buffed и золото Dragon Slayer

Сборка кладёт его правкой VMT карточки, как если бы человек вставил его в
редакторе сам: правка живёт в работе, отменяется вместе с War Paint и видна в
редакторе. `$basetexture` берётся из игрового VMT карточки - тогда сборка сама
переведёт его на текстуру мода (main_texture._write_main_vmt). Своя правка
помечена первой строкой: по ней следующий War Paint знает, что её можно
заменить или снять, а правку человека - нет
"""

from __future__ import annotations

import re
from typing import Optional

#: Первая строка правки, которую положил War Paint
MARK = '// War Paint: '

_BASETEXTURE = re.compile(r'^([ \t]*)"?\$basetexture"?[ \t]+("[^"\n]*"|\S+)',
                          re.IGNORECASE | re.MULTILINE)


def override_path(defs, kit_id: int, item_def: int) -> str:
    """Материал, который игра надевает на пушку с этим War Paint, без
    `materials/` и расширения. Пусто - стоковый"""
    from src.data.paintkit_defs import find_item

    _kit, item = find_item(defs, int(kit_id), int(item_def)) if defs else (None, None)
    path = (item.material_override if item else '') or ''
    return path.replace('\\', '/').strip().strip('/').removesuffix('.vmt')


def read(paks: list, override: str) -> Optional[str]:
    """Текст VMT материала из архивов игры, None - его там нет"""
    from src.services.vtf_preview_service import read_from_vpks

    raw = read_from_vpks(paks, f'materials/{override}.vmt') if override else None
    return raw.decode('utf-8', errors='replace') if raw else None


def compose(override_text: str, game_vmt: str, kit_name: str) -> Optional[str]:
    """
    Правка VMT карточки: материал War Paint с `$basetexture` игрового VMT
    карточки. None - в игровом VMT нет текстуры, и подставить нечего

    Путь именно игровой, а не из материала War Paint: у синей карточки он
    свой, а сборка переводит на текстуру мода только совпавший с игрой путь
    """
    from src.services import vmt_parse

    base = vmt_parse.basetexture(game_vmt or '')
    if not base:
        return None
    line = f'"$baseTexture" "{base}"'
    # Из архива приходят строки с \r\n: без этого правка была бы со смешанными
    body = override_text.replace('\r\n', '\n')
    body, found = _BASETEXTURE.subn(lambda m: m.group(1) + line, body, count=1)
    if not found:
        body = override_text.replace('{', '{\n\t' + line, 1)
    return f'{MARK}{kit_name}\n{body.lstrip()}'


def is_war_paint(text: Optional[str]) -> bool:
    """Правку положил War Paint, а не человек"""
    return bool(text) and text.lstrip().startswith(MARK)
