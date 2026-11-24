"""
Снимок модели из вьювера - обложкой карточки (мод библиотеки, своя работа)

Байты приходят со страницы, поэтому PNG проверяется разбором, а не на слово,
и пишется через временный файл: оборванная запись не должна оставить битую
обложку, которая к тому же считалась бы готовой
"""

from __future__ import annotations

import os
from io import BytesIO
from pathlib import Path
from typing import Optional

from src.shared.logging_config import get_logger

logger = get_logger(__name__)

#: Крупнее не нужно: карточка в каталоге размером с ноготь
ICON_SIZE = 256
#: Потолок присланного снимка. Вьювер шлёт 512, всё сверх - не от него
MAX_BYTES = 2 * 1024 * 1024


def write_png(png: bytes, out: Path) -> Optional[Path]:
    """Проверяет PNG, ужимает до ICON_SIZE и кладёт в out. None - не картинка"""
    from PIL import Image, UnidentifiedImageError

    if not png or len(png) > MAX_BYTES:
        return None
    tmp = out.with_suffix('.tmp')
    try:
        with Image.open(BytesIO(png)) as img:
            # Размер из заголовка, до распаковки: маленький PNG может
            # развернуться в гигабайты
            if img.format != 'PNG' or max(img.size) > 4 * ICON_SIZE:
                return None
            img.load()
            img.thumbnail((ICON_SIZE, ICON_SIZE))
            img.save(tmp, 'PNG')
    except (UnidentifiedImageError, OSError, ValueError) as exc:
        logger.warning(f"снимок {out.name} не принят: {exc}")
        return None
    os.replace(tmp, out)
    return out
