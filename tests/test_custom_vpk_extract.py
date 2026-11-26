"""Распаковка VPK мода: чужой архив не пишет за пределы своей папки"""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from src.services.custom_vpk_service import CustomVPKService


class _FakePak(dict):
    """Архив с заданными именами: настоящий VPK с «..» библиотекой не собрать"""

    def __getitem__(self, name):
        data = super().__getitem__(name)
        return type("Entry", (), {"read": lambda self: data})()


class ExtractTests(unittest.TestCase):
    BAD = ("../evil.txt", "materials/../../evil.txt", "..\\evil.txt",
           "C:/evil.txt", "/../evil.txt", "\\\\host\\share\\evil.txt")

    def test_archive_with_outside_path_is_refused_before_any_write(self):
        for name in self.BAD:
            with self.subTest(name=name), tempfile.TemporaryDirectory() as tmp:
                out_dir = Path(tmp) / "out"
                pak = _FakePak({"materials/ok.vmt": b"ok", name: b"evil"})
                with patch("vpk.open", return_value=pak):
                    ok = CustomVPKService.extract_vpk_to_dir("mod.vpk", str(out_dir))
                self.assertFalse(ok)
                self.assertEqual([p for p in Path(tmp).rglob("*") if p.is_file()], [])

    def test_ordinary_archive_is_extracted(self):
        with tempfile.TemporaryDirectory() as tmp:
            out_dir = Path(tmp) / "out"
            pak = _FakePak({"materials/models/a/b.vtf": b"x", "models/a.mdl": b"y"})
            with patch("vpk.open", return_value=pak):
                self.assertTrue(CustomVPKService.extract_vpk_to_dir("mod.vpk", str(out_dir)))
            self.assertEqual((out_dir / "models" / "a.mdl").read_bytes(), b"y")

    def test_unreadable_archive_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            bad = Path(tmp) / "bad.vpk"
            bad.write_bytes(b"not a vpk")
            self.assertFalse(CustomVPKService.extract_vpk_to_dir(str(bad), str(Path(tmp) / "out")))


if __name__ == "__main__":
    unittest.main()
