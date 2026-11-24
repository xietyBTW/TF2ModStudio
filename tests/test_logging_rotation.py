"""Ротация лога, когда файл держит другой процесс"""

import logging
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from src.shared.logging_config import SafeRotatingFileHandler


def _record(text: str) -> logging.LogRecord:
    return logging.LogRecord('t', logging.INFO, __file__, 0, text, None, None)


class SafeRotationTests(unittest.TestCase):
    def test_locked_file_keeps_logging_and_rotates_later(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / 'app.log'
            handler = SafeRotatingFileHandler(log, maxBytes=100, backupCount=2,
                                              encoding='utf-8')
            errors = []
            handler.handleError = errors.append
            try:
                busy = PermissionError(32, 'занят другим процессом')
                with mock.patch.object(handler, 'rotate', side_effect=busy) as rotate:
                    for i in range(20):
                        handler.emit(_record(f'строка {i} ' + 'x' * 20))
                self.assertEqual(errors, [])
                self.assertEqual(rotate.call_count, 1)    # дальше ждёт, а не долбит
                self.assertIn('строка 19', log.read_text(encoding='utf-8'))

                handler._retry_at = 0.0                     # время ожидания вышло
                handler.emit(_record('после'))
                self.assertTrue((Path(tmp) / 'app.log.1').is_file())
                self.assertEqual(errors, [])
            finally:
                handler.close()


if __name__ == '__main__':
    unittest.main()
