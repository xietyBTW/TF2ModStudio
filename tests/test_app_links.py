"""Ссылки автора из links.json: проверка адресов, слои, отчёт об ошибке"""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from src.services import app_links

ROOT = Path(__file__).resolve().parent.parent


class CleanTests(unittest.TestCase):
    def test_repo_file_passes_whole(self):
        raw = json.loads((ROOT / 'links.json').read_text(encoding='utf-8'))
        self.assertEqual(app_links.clean(raw), raw)

    def test_defaults_pass_whole(self):
        self.assertEqual(app_links.clean(app_links.DEFAULTS), app_links.DEFAULTS)

    def test_bad_values_dropped_one_by_one(self):
        got = app_links.clean({
            'discord': 'http://discord.com/users/1',        # не https
            'steam': 'https://steamcommunity.com.evil.io/x',  # чужой хост
            'support': 'https://boosty.to/someone',
            'issues': 'javascript:alert(1)',
            'discord_name': 'Has Spaces',
            'unknown': 'https://github.com',
        })
        self.assertEqual(got, {'support': 'https://boosty.to/someone'})

    def test_not_a_dict(self):
        self.assertEqual(app_links.clean(['https://github.com']), {})


class LayerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        patcher = mock.patch.object(app_links, 'data_dir',
                                    return_value=Path(self.tmp.name))
        patcher.start()
        self.addCleanup(patcher.stop)
        self.addCleanup(self.tmp.cleanup)

    def test_offline_first_run_gives_defaults(self):
        with mock.patch.object(app_links, '_download', return_value=None):
            self.assertEqual(app_links.fetch_links(), app_links.DEFAULTS)

    def test_fresh_link_survives_going_offline(self):
        new = 'https://steamcommunity.com/tradeoffer/new/?partner=1&token=NEW'
        with mock.patch.object(app_links, '_download',
                               return_value={'support': new}):
            self.assertEqual(app_links.fetch_links()['support'], new)
        with mock.patch.object(app_links, '_download', return_value=None):
            links = app_links.fetch_links()
        self.assertEqual(links['support'], new)
        self.assertEqual(links['discord'], app_links.DEFAULTS['discord'])
        self.assertEqual(app_links.cached_links()['support'], new)

    def test_broken_cache_file_ignored(self):
        path = Path(self.tmp.name) / 'cache' / 'links.json'
        path.parent.mkdir(parents=True)
        path.write_text('{not json', encoding='utf-8')
        self.assertEqual(app_links.cached_links(), app_links.DEFAULTS)


class ReportTests(unittest.TestCase):
    def test_home_folder_masked(self):
        from src.app.api import about

        home = str(Path.home())
        text = about._mask_home(f'open {home}\\work\\x.vtf and '
                                f"{home.replace(chr(92), '/').upper()}/y")
        self.assertNotIn(Path.home().name, text.replace('~', ''))
        self.assertIn('~\\work\\x.vtf', text)

    def test_report_has_version(self):
        from src.app.api import about
        from src.shared.version import __version__

        self.assertIn(__version__, about.report_info()['text'])


if __name__ == '__main__':
    unittest.main()
