"""
Есть ли у окна приложения движок

Окно рисует Microsoft Edge WebView2. Без него pywebview молча берёт движок
Internet Explorer, а тот не исполняет модули страницы: окно оставалось пустым
без единого слова. Так бывает на урезанных сборках Windows, где вычищен Edge

Вторая причина не связана с WebView2. Окно держится на .NET (pythonnet), а
.NET Framework не загружает сборки с меткой «скачано из интернета». Проводник
ставит её на каждый файл, распакованный из скачанного zip, и портативная
версия говорила «нет WebView2» там, где он был
"""

from __future__ import annotations

import ctypes
import os
import sys
import webbrowser
from pathlib import Path
from typing import Optional

#: Страница Microsoft для обычных людей, а не для разработчиков
DOWNLOAD_URL = "https://developer.microsoft.com/microsoft-edge/webview2/consumer/"

_TEXT = {
    'ru': ("TF2 Mod Studio",
           "Для окна TF2 Mod Studio нужен компонент Microsoft Edge WebView2, "
           "а на этом компьютере его нет.\n\n"
           "Сейчас приложение откроется в браузере. Чтобы вернуть обычное окно, "
           "установите WebView2 и запустите приложение снова.\n\n"
           "Открыть страницу загрузки WebView2?"),
    'en': ("TF2 Mod Studio",
           "TF2 Mod Studio needs Microsoft Edge WebView2 for its window, "
           "and it isn't installed on this computer.\n\n"
           "The app will open in your browser for now. To get the normal window "
           "back, install WebView2 and start the app again.\n\n"
           "Open the WebView2 download page?"),
}

_BLOCKED_TEXT = {
    'ru': ("TF2 Mod Studio",
           "Windows не дала загрузить компоненты окна TF2 Mod Studio (.NET).\n\n"
           "Так бывает с архивом, скачанным из интернета. Нажмите правой кнопкой "
           "на скачанный zip, откройте «Свойства», отметьте «Разблокировать» и "
           "распакуйте его заново. Или поставьте приложение установщиком.\n\n"
           "Сейчас приложение откроется в браузере."),
    'en': ("TF2 Mod Studio",
           "Windows did not let TF2 Mod Studio load the components of its "
           "window (.NET).\n\n"
           "This happens with an archive downloaded from the internet. "
           "Right-click the downloaded zip, open Properties, tick Unblock and "
           "extract it again. Or install the app with the installer.\n\n"
           "The app will open in your browser for now."),
}

_MB_OK = 0x00
_MB_YESNO = 0x04
_MB_ICONWARNING = 0x30
_MB_SETFOREGROUND = 0x10000
_IDYES = 6

#: Пакеты со сборками .NET, без которых окно не поднимается
_DOTNET_PACKAGES = ('pythonnet', 'clr_loader', 'webview')


def unblock_own_libraries(root: Optional[str] = None) -> int:
    """
    Снимает метку «скачано из интернета» со сборок .NET самого приложения

    То же, что галка «Разблокировать» в свойствах zip, только для своих
    файлов и до первого обращения к .NET. Установщик меток не ставит, а у
    запуска из исходников их нет - тогда ничего не делаем

    Returns:
        Сколько меток снято
    """
    base = root or getattr(sys, '_MEIPASS', None)
    if not base:
        return 0
    removed = 0
    for package in _DOTNET_PACKAGES:
        for dll in Path(base, package).rglob('*.dll'):
            try:
                os.remove(f'{dll}:Zone.Identifier')
                removed += 1
            except OSError:
                pass   # метки нет или папка только для чтения
    return removed


def engine_problem() -> Optional[str]:
    """Почему окно не откроется: None - всё в порядке, 'missing' - нет
    WebView2 (pywebview взял бы Internet Explorer), 'blocked' - .NET не
    поднялся (сборки заблокированы, нет .NET Framework)"""
    try:
        # Тот же выбор, что сделает сам pywebview при открытии окна
        from webview.platforms import winforms
    except Exception:  # noqa: BLE001
        return 'blocked'
    return None if winforms.renderer == 'edgechromium' else 'missing'


def engine_ok() -> bool:
    """True - pywebview откроет окно на WebView2, а не на Internet Explorer"""
    return engine_problem() is None


def _language() -> str:
    """Язык Windows: окно показывается до того, как человек выбрал язык"""
    try:
        lang_id = ctypes.windll.kernel32.GetUserDefaultUILanguage()
    except (AttributeError, OSError):
        return 'en'
    return 'ru' if lang_id & 0x3FF == 0x19 else 'en'


def explain_blocked() -> None:
    """Объясняет, почему окно в браузере, когда WebView2 есть, а .NET нет"""
    title, text = _BLOCKED_TEXT[_language()]
    try:
        ctypes.windll.user32.MessageBoxW(
            None, text, title, _MB_OK | _MB_ICONWARNING | _MB_SETFOREGROUND)
    except (AttributeError, OSError):
        pass


def offer_install() -> None:
    """Объясняет, почему окно в браузере, и предлагает страницу загрузки"""
    title, text = _TEXT[_language()]
    try:
        answer = ctypes.windll.user32.MessageBoxW(
            None, text, title, _MB_YESNO | _MB_ICONWARNING | _MB_SETFOREGROUND)
    except (AttributeError, OSError):
        return
    if answer == _IDYES:
        webbrowser.open(DOWNLOAD_URL)
