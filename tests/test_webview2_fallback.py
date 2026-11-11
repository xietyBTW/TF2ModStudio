"""
Без WebView2 окно не открывается пустым: человек видит объяснение, а
приложение уходит в браузер и закрывается вместе с его вкладкой
"""

import sys
import types
import unittest
from unittest import mock

from frontend import app, webview2_check


def _fake_winforms(renderer):
    platforms = types.ModuleType('webview.platforms')
    winforms = types.ModuleType('webview.platforms.winforms')
    winforms.renderer = renderer
    platforms.winforms = winforms
    return {'webview.platforms': platforms, 'webview.platforms.winforms': winforms}


class EngineTests(unittest.TestCase):
    def test_webview2_is_ok(self):
        with mock.patch.dict(sys.modules, _fake_winforms('edgechromium')):
            self.assertTrue(webview2_check.engine_ok())

    def test_internet_explorer_fallback_is_not(self):
        with mock.patch.dict(sys.modules, _fake_winforms('mshtml')):
            self.assertFalse(webview2_check.engine_ok())

    def test_yes_opens_the_download_page(self):
        with mock.patch.object(webview2_check, '_language', return_value='ru'), \
             mock.patch('ctypes.windll.user32.MessageBoxW', return_value=6, create=True), \
             mock.patch.object(webview2_check.webbrowser, 'open') as opened:
            webview2_check.offer_install()
        opened.assert_called_once_with(webview2_check.DOWNLOAD_URL)

    def test_no_opens_nothing(self):
        with mock.patch('ctypes.windll.user32.MessageBoxW', return_value=7, create=True), \
             mock.patch.object(webview2_check.webbrowser, 'open') as opened:
            webview2_check.offer_install()
        opened.assert_not_called()

    def test_window_is_not_opened_without_webview2(self):
        """pywebview на движке IE показал бы пустое окно"""
        fake_webview = types.ModuleType('webview')
        with mock.patch.dict(sys.modules, {'webview': fake_webview}), \
             mock.patch.object(webview2_check, 'engine_ok', return_value=False), \
             mock.patch.object(webview2_check, 'offer_install') as offered:
            self.assertFalse(app._open_pywebview('http://127.0.0.1:1/?', {'theme': 'dark'}))
        offered.assert_called_once()


class _Server:
    def __init__(self, listeners):
        self._listeners = iter(listeners)
        self.ever_listened = False

    @property
    def listeners(self):
        value = next(self._listeners)
        self.ever_listened = self.ever_listened or value > 0
        return value


class WaitForTabTests(unittest.TestCase):
    def _wait(self, listeners, grace=10.0):
        clock = iter(range(0, 10_000, 2))
        with mock.patch.object(app.time, 'sleep'), \
             mock.patch.object(app.time, 'monotonic', side_effect=lambda: next(clock)):
            app._wait_while_page_open(_Server(listeners), grace=grace)

    def test_returns_after_the_tab_is_gone(self):
        # Вкладка была открыта, потом пропала дольше чем на grace
        self._wait([1, 1, 1] + [0] * 20)

    def test_short_reload_does_not_end_it(self):
        listeners = [1, 0, 1, 1] + [0] * 20
        server = _Server(listeners)
        clock = iter(range(0, 10_000, 2))
        with mock.patch.object(app.time, 'sleep'), \
             mock.patch.object(app.time, 'monotonic', side_effect=lambda: next(clock)):
            app._wait_while_page_open(server, grace=10.0)
        # Короткий обрыв пережит, выход случился уже во время второго,
        # долгого пропадания: часть его нулей осталась непрочитанной
        rest = list(server._listeners)
        self.assertTrue(0 < len(rest) < 20, rest)
