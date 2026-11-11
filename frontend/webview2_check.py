"""
Есть ли у окна приложения движок

Окно рисует Microsoft Edge WebView2. Без него pywebview молча берёт движок
Internet Explorer, а тот не исполняет модули страницы: окно оставалось пустым
без единого слова. Так бывает на урезанных сборках Windows, где вычищен Edge
"""

from __future__ import annotations

import ctypes
import webbrowser

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

_MB_YESNO = 0x04
_MB_ICONWARNING = 0x30
_MB_SETFOREGROUND = 0x10000
_IDYES = 6


def engine_ok() -> bool:
    """True - pywebview откроет окно на WebView2, а не на Internet Explorer"""
    try:
        # Тот же выбор, что сделает сам pywebview при открытии окна
        from webview.platforms import winforms
    except Exception:  # noqa: BLE001 - нет .NET Framework или pythonnet не поднялся
        return False
    return winforms.renderer == 'edgechromium'


def _language() -> str:
    """Язык Windows: окно показывается до того, как человек выбрал язык"""
    try:
        lang_id = ctypes.windll.kernel32.GetUserDefaultUILanguage()
    except (AttributeError, OSError):
        return 'en'
    return 'ru' if lang_id & 0x3FF == 0x19 else 'en'


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
