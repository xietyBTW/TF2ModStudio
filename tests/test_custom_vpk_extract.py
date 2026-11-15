"""
Тесты распаковки VPK в CustomVPKService._extract_via_vpk_exe

Регрессия: модуль использовал `subprocess` и `ToolPaths` без импорта - вызов
падал с NameError на первой же строке (ToolPaths.get_vpk_tool() вне try/except),
ломая быстрый путь распаковки через vpk.exe. Эти тесты гарантируют, что путь
работает и имена доступны
"""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from src.services.custom_vpk_service import CustomVPKService


def _fake_completed(returncode=0, stdout="", stderr=""):
    return type("R", (), {"returncode": returncode, "stdout": stdout, "stderr": stderr})()


class ExtractViaVpkExeTests(unittest.TestCase):
    def test_module_has_subprocess_and_toolpaths(self):
        # Прямая защита от регрессии отсутствующих импортов: оба имени должны
        # быть доступны в неймспейсе модуля (иначе путь падает с NameError)
        import src.services.custom_vpk_service as mod
        self.assertTrue(hasattr(mod, "subprocess"))
        self.assertTrue(hasattr(mod, "ToolPaths"))
        self.assertTrue(hasattr(mod, "ToolTimeouts"))

    def test_success_returns_true_when_files_extracted(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            out_dir = base / "out"
            out_dir.mkdir()
            vpk_tool = base / "vpk.exe"
            vpk_tool.write_bytes(b"stub")  # ToolPaths.get_vpk_tool().exists() -> True

            def fake_run(*args, **kwargs):
                # Эмулируем успешную распаковку: vpk.exe создаёт файл
                (out_dir / "extracted.txt").write_text("data")
                return _fake_completed(returncode=0)

            with patch("src.services.custom_vpk_service.ToolPaths.get_vpk_tool", return_value=vpk_tool):
                with patch("src.services.custom_vpk_service.subprocess.run", side_effect=fake_run):
                    ok = CustomVPKService._extract_via_vpk_exe("mod.vpk", str(out_dir))
            self.assertTrue(ok)

    def test_missing_tool_returns_false(self):
        with tempfile.TemporaryDirectory() as tmp:
            out_dir = Path(tmp) / "out"
            out_dir.mkdir()
            missing = Path(tmp) / "does_not_exist" / "vpk.exe"
            with patch("src.services.custom_vpk_service.ToolPaths.get_vpk_tool", return_value=missing):
                ok = CustomVPKService._extract_via_vpk_exe("mod.vpk", str(out_dir))
            self.assertFalse(ok)

    def test_nonzero_returncode_returns_false(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            out_dir = base / "out"
            out_dir.mkdir()
            vpk_tool = base / "vpk.exe"
            vpk_tool.write_bytes(b"stub")
            with patch("src.services.custom_vpk_service.ToolPaths.get_vpk_tool", return_value=vpk_tool):
                with patch("src.services.custom_vpk_service.subprocess.run",
                           return_value=_fake_completed(returncode=1, stderr="boom")):
                    ok = CustomVPKService._extract_via_vpk_exe("mod.vpk", str(out_dir))
            self.assertFalse(ok)


class _FakePak(dict):
    """Архив с заданными именами: настоящий VPK с «..» библиотекой не собрать"""

    def __getitem__(self, name):
        data = super().__getitem__(name)
        return type("Entry", (), {"read": lambda self: data})()


class EntryOutsideTests(unittest.TestCase):
    BAD = ("../evil.txt", "materials/../../evil.txt", "..\\evil.txt",
           "C:/evil.txt", "/../evil.txt", "\\\\host\\share\\evil.txt")

    def test_archive_with_outside_path_is_refused_before_any_tool(self):
        for name in self.BAD:
            with self.subTest(name=name), tempfile.TemporaryDirectory() as tmp:
                out_dir = Path(tmp) / "out"
                pak = _FakePak({"materials/ok.vmt": b"ok", name: b"evil"})
                with patch("vpk.open", return_value=pak), \
                     patch("src.services.custom_vpk_service.subprocess.run") as run:
                    ok = CustomVPKService.extract_vpk_to_dir("mod.vpk", str(out_dir))
                self.assertFalse(ok)
                run.assert_not_called()
                self.assertEqual([p for p in Path(tmp).rglob("*") if p.is_file()], [])

    def test_ordinary_archive_passes(self):
        with tempfile.TemporaryDirectory() as tmp:
            pak = _FakePak({"materials/models/a/b.vtf": b"x", "models/a.mdl": b"y"})
            with patch("vpk.open", return_value=pak):
                self.assertIsNone(CustomVPKService._entry_outside("mod.vpk", tmp))

    def test_python_fallback_never_writes_outside(self):
        with tempfile.TemporaryDirectory() as tmp:
            out_dir = Path(tmp) / "out"
            out_dir.mkdir()
            pak = _FakePak({"materials/ok.vmt": b"ok", "../evil.txt": b"evil"})
            with patch("vpk.open", return_value=pak):
                ok = CustomVPKService._extract_via_python_vpk("mod.vpk", str(out_dir))
            self.assertTrue(ok)
            self.assertTrue((out_dir / "materials" / "ok.vmt").is_file())
            self.assertFalse((Path(tmp) / "evil.txt").exists())


if __name__ == "__main__":
    unittest.main()
