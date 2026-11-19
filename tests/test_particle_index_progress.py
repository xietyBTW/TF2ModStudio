"""
Прогресс сбора индекса эффектов частиц

Скан всех PCF игры с нуля идёт секунд пятнадцать, и список эффектов
показывает, сколько файлов уже пройдено
"""

import unittest
from unittest.mock import patch

from src.services.particle_editor import catalog
from src.services.particle_editor_service import ParticleEditorService as PES


class ProgressTests(unittest.TestCase):
    def setUp(self):
        self._saved = (PES._attr_catalog, PES._catalog_progress)
        PES._attr_catalog = {}

    def tearDown(self):
        PES._attr_catalog, PES._catalog_progress = self._saved

    def _scan(self, fail_at=None):
        seen = []

        def scan(cls, root, pcf, *rest):
            seen.append(PES.catalog_progress())
            if pcf == fail_at:
                raise RuntimeError("битый архив")

        with patch.object(catalog, "load_disk_catalog", return_value=False), \
                patch.object(PES, "list_game_pcfs", return_value=["a.pcf", "b.pcf", "c.pcf"]), \
                patch.object(catalog, "_scan_pcf", side_effect=scan):
            try:
                PES.build_attr_catalog("D:/tf2")
            except RuntimeError:
                pass
        return seen

    def test_files_are_counted_while_scanning(self):
        self.assertEqual(self._scan(), [(0, 3), (1, 3), (2, 3)])
        self.assertIsNone(PES.catalog_progress(), "скан окончен - полосы нет")

    def test_failed_scan_does_not_leave_the_bar(self):
        self._scan(fail_at="b.pcf")
        self.assertIsNone(PES.catalog_progress())


if __name__ == "__main__":
    unittest.main()
