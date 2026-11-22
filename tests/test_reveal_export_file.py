"""«Показать в папке» открывает проводник только для файлов папки экспорта"""

import tempfile
import unittest
from pathlib import Path
from unittest import mock

from src.app.api.app_log import reveal_export_file


class RevealExportFileTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.export = root / 'export'
        self.export.mkdir()
        self.outside = root / 'secret.txt'
        self.outside.write_text('x')
        patcher = mock.patch('src.shared.paths.export_dir', return_value=self.export)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.addCleanup(self.tmp.cleanup)

    def test_file_outside_export_is_refused(self):
        with mock.patch('subprocess.Popen') as popen:
            self.assertIn('error', reveal_export_file(str(self.outside)))
            popen.assert_not_called()

    def test_escape_through_dotdot_is_refused(self):
        sneaky = self.export / '..' / 'secret.txt'
        with mock.patch('subprocess.Popen') as popen:
            self.assertIn('error', reveal_export_file(str(sneaky)))
            popen.assert_not_called()

    def test_missing_file_is_refused(self):
        with mock.patch('subprocess.Popen') as popen:
            self.assertIn('error', reveal_export_file(str(self.export / 'none.wav')))
            popen.assert_not_called()

    def test_file_inside_export_is_shown(self):
        wav = self.export / 'crit_power.wav'
        wav.write_bytes(b'RIFF')
        with mock.patch('sys.platform', 'win32'), mock.patch('subprocess.Popen') as popen:
            self.assertTrue(reveal_export_file(str(wav)).get('opened'))
            popen.assert_called_once()
            self.assertIn('/select,', popen.call_args.args[0])


if __name__ == '__main__':
    unittest.main()
