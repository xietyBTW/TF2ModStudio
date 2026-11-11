"""
Ссылки автора: Discord, Steam, поддержка, баг-трекер

Адреса лежат в links.json в корне репозитория, и приложение берёт его с
GitHub. Ссылка обмена Steam меняется кнопкой «Создать новую ссылку», и вшитый
адрес умер бы во всех выпущенных версиях разом. Порядок такой:

  вшитые DEFAULTS  <-  последний скачанный файл  <-  свежий файл с GitHub

Каждый слой подменяет только те ключи, что прошли проверку: опечатка в одном
адресе не гасит остальные. Пропускаем только https на известные сайты, иначе
одна правка файла превращала бы кнопку в ссылку куда угодно
"""

from __future__ import annotations

import json
import re
import urllib.error
import urllib.request
from pathlib import Path
from typing import Dict, Mapping, Optional
from urllib.parse import urlsplit

from src.shared.logging_config import get_logger
from src.shared.paths import data_dir
from src.shared.version import GITHUB_OWNER, GITHUB_REPO, __version__

logger = get_logger(__name__)

REMOTE_URL = (f"https://raw.githubusercontent.com/{GITHUB_OWNER}/{GITHUB_REPO}"
              "/main/links.json")
_TIMEOUT = 5
#: Файл из десятка строк. Больше - значит, отдали что-то не то
_MAX_BYTES = 16 * 1024

DEFAULTS: Dict[str, str] = {
    # По числовому ID: ник в Discord можно сменить, ID нет
    'discord': 'https://discord.com/users/462488438072147988',
    'discord_name': 'xiety_btw',
    # /profiles/<SteamID64> живёт вечно, в отличие от /id/<имя>
    'steam': 'https://steamcommunity.com/profiles/76561198355080052',
    'support': ('https://steamcommunity.com/tradeoffer/new/'
                '?partner=394814324&token=GNGCagXk'),
    'issues': f'https://github.com/{GITHUB_OWNER}/{GITHUB_REPO}/issues/new',
}

#: Куда может вести каждый адрес. Поддомены разрешены (www.)
_HOSTS: Dict[str, tuple] = {
    'discord': ('discord.com', 'discord.gg'),
    'steam': ('steamcommunity.com',),
    'support': ('steamcommunity.com', 'boosty.to', 'ko-fi.com',
                'patreon.com', 'donationalerts.com'),
    'issues': ('github.com',),
}
#: Правила имён пользователя Discord: строчные, цифры, «_» и «.», 2-32
_DISCORD_NAME = re.compile(r'^[a-z0-9_.]{2,32}$')


def _cache_file() -> Path:
    return data_dir() / 'cache' / 'links.json'


def _host_ok(url: str, allowed: tuple) -> bool:
    parts = urlsplit(url)
    host = (parts.hostname or '').lower()
    return (parts.scheme == 'https'
            and any(host == h or host.endswith('.' + h) for h in allowed))


def clean(raw: object) -> Dict[str, str]:
    """Только известные ключи с годными значениями, остальное молча мимо"""
    if not isinstance(raw, Mapping):
        return {}
    out: Dict[str, str] = {}
    for key, allowed in _HOSTS.items():
        value = raw.get(key)
        if isinstance(value, str) and _host_ok(value.strip(), allowed):
            out[key] = value.strip()
    name = raw.get('discord_name')
    if isinstance(name, str) and _DISCORD_NAME.match(name.strip()):
        out['discord_name'] = name.strip()
    return out


def _read_cache() -> Dict[str, str]:
    try:
        return clean(json.loads(_cache_file().read_text(encoding='utf-8')))
    except (OSError, ValueError):
        return {}


def cached_links() -> Dict[str, str]:
    """Без сети: вшитые адреса поверх них последний скачанный файл"""
    return {**DEFAULTS, **_read_cache()}


def _download() -> Optional[Dict[str, str]]:
    req = urllib.request.Request(
        REMOTE_URL, headers={'User-Agent': f'TF2ModStudio/{__version__}'})
    try:
        with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:
            body = resp.read(_MAX_BYTES + 1)
        if len(body) > _MAX_BYTES:
            raise ValueError(f'over {_MAX_BYTES} bytes')
        return clean(json.loads(body.decode('utf-8')))
    except (urllib.error.URLError, OSError, ValueError) as exc:
        logger.debug(f"Ссылки автора не скачались: {exc}")
        return None


def fetch_links() -> Dict[str, str]:
    """
    Свежие адреса с GitHub, а без сети - те, что уже есть

    Удачный ответ запоминается на диск: без сети в следующий раз покажется
    он, а не вшитые адреса этой версии
    """
    fresh = _download()
    if not fresh:
        return cached_links()
    try:
        path = _cache_file()
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix('.tmp')
        tmp.write_text(json.dumps(fresh, ensure_ascii=False), encoding='utf-8')
        tmp.replace(path)
    except OSError as exc:
        logger.debug(f"Ссылки автора не сохранены: {exc}")
    return {**DEFAULTS, **fresh}
