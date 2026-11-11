"""Вкладка «О программе»: ссылки автора и сведения для отчёта об ошибке"""

from __future__ import annotations

import platform
import re
from pathlib import Path
from typing import Dict, List

from src.app.api._common import endpoint

#: Ссылки с GitHub на сеанс: адреса меняются раз в год, а не между открытиями
#: настроек
_links: Dict[str, str] = {}

#: Сколько последних предупреждений и ошибок журнала класть в отчёт
_REPORT_LOG_LINES = 40


@endpoint
def app_links() -> Dict[str, str]:
    """Свежие ссылки автора. Ходит в сеть один раз за сеанс"""
    from src.services.app_links import fetch_links

    if not _links:
        _links.update(fetch_links())
    return dict(_links)


@endpoint
def report_info() -> Dict[str, str]:
    """
    Текст для отчёта об ошибке: версия, система и последние ошибки журнала

    По-английски: читать его автору, а не тому, кто копирует. Домашняя папка
    заменена на «~», чтобы в отчёт не уходило имя пользователя Windows
    """
    lines = [*_about_lines(), '', 'Recent warnings and errors:']
    lines += _log_lines() or ['(none)']
    return {'text': _mask_home('\n'.join(lines))}


def _about_lines() -> List[str]:
    from src.config.app_config import AppConfig
    from src.services.tf2_paths import TF2Paths
    from src.services.update_checker import portable_dir
    from src.shared.paths import is_frozen
    from src.shared.version import __version__

    kind = ('portable' if portable_dir() else 'installed') if is_frozen() \
        else 'from source'
    cfg = AppConfig.load_config()
    return [
        f'TF2 Mod Studio {__version__} ({kind})',
        f'{platform.system()} {platform.release()} ({platform.version()})',
        f"Language: {cfg.get('language') or 'en'}",
        'TF2 folder: ' + ('found' if TF2Paths.is_valid(
            cfg.get('tf2_game_folder') or '') else 'not found'),
    ]


def _log_lines() -> List[str]:
    import time
    from src.shared import log_bridge

    entries = [e for e in log_bridge.tail(0, 5000)['entries']
               if e['level'] in ('WARNING', 'ERROR', 'CRITICAL')]
    return [f"{time.strftime('%H:%M:%S', time.localtime(e['time']))} "
            f"{e['level']} {e['source']}: {e['text']}"
            for e in entries[-_REPORT_LOG_LINES:]]


def _mask_home(text: str) -> str:
    home = str(Path.home())
    for variant in {home, home.replace('\\', '/')}:
        text = re.sub(re.escape(variant), '~', text, flags=re.IGNORECASE)
    return text
