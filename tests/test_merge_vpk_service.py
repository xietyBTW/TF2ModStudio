import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from src.services.merge_vpk_service import MergeVPKService
from src.shared.exceptions import VPKCreationError, RequiredFileMissingError


class FakeEntry:
    def __init__(self, data: bytes):
        self._data = data

    def read(self) -> bytes:
        return self._data


class FakeVPK:
    def __init__(self, files):
        self._files = files

    def __iter__(self):
        return iter(self._files.keys())

    def __getitem__(self, key):
        return FakeEntry(self._files[key])


class MergeVpkServiceTests(unittest.TestCase):
    def test_merge_vpk_files_library_missing(self):
        with patch("src.services.merge_vpk_service.VPK_AVAILABLE", False):
            success, message = MergeVPKService.merge_vpk_files([], "out.vpk")
        self.assertFalse(success)
        self.assertTrue(message)

    def test_merge_vpk_files_no_files(self):
        with patch("src.services.merge_vpk_service.VPK_AVAILABLE", True):
            success, message = MergeVPKService.merge_vpk_files([], "out.vpk")
        self.assertFalse(success)
        self.assertTrue(message)

    def test_merge_vpk_files_missing_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            vpk_path = base / "missing.vpk"
            with patch("src.services.merge_vpk_service.VPK_AVAILABLE", True):
                success, message = MergeVPKService.merge_vpk_files([vpk_path], "out.vpk")
            self.assertFalse(success)
            self.assertIn("missing", message)

    def test_merge_vpk_files_success(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            vpk_path = base / "a.vpk"
            vpk_path.write_bytes(b"data")
            fake_files = {"models/a.mdl": b"mdl"}
            with patch("src.services.merge_vpk_service.VPK_AVAILABLE", True):
                with patch("src.services.merge_vpk_service.vpk.open", return_value=FakeVPK(fake_files)):
                    with patch("src.services.merge_vpk_service.MergeVPKService._create_vpk_from_directory", return_value=str(base / "out.vpk")):
                        success, message = MergeVPKService.merge_vpk_files([vpk_path], "out.vpk", export_folder=str(base))
                        self.assertTrue(success)
                        self.assertIn("out.vpk", message)

    def test_merge_directory_keeps_the_file_of_the_mod_above(self):
        # Копия под другим именем (file_1.txt) игре не видна - это мусор в VPK.
        # Остаётся файл мода, который выше в списке и пришёл первым
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            source = base / "source"
            target = base / "target"
            (source / "folder").mkdir(parents=True)
            (target / "folder").mkdir(parents=True)
            (source / "folder" / "file.txt").write_text("a", encoding="utf-8")
            (target / "folder" / "file.txt").write_text("b", encoding="utf-8")
            (source / "folder" / "new.txt").write_text("c", encoding="utf-8")
            MergeVPKService._merge_directory(source, target)
            files = sorted(p.name for p in (target / "folder").iterdir())
            self.assertEqual(files, ["file.txt", "new.txt"])
            self.assertEqual((target / "folder" / "file.txt").read_text(encoding="utf-8"), "b")
    
    def test_merge_vpk_files_cancel(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            vpk_path = base / "a.vpk"
            vpk_path.write_bytes(b"data")
            fake_files = {"models/a.mdl": b"mdl"}
            with patch("src.services.merge_vpk_service.vpk.open", return_value=FakeVPK(fake_files)):
                success, message = MergeVPKService.merge_vpk_files(
                    [vpk_path],
                    "out.vpk",
                    export_folder=str(base),
                    should_cancel=lambda: True
                )
            self.assertFalse(success)
            self.assertTrue(message)

    def test_create_vpk_from_directory_success(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            vpkroot = base / "vpkroot"
            vpkroot.mkdir()
            def fake_run(*args, **kwargs):
                (base / "vpkroot.vpk").write_bytes(b"vpk")
                return type("R", (), {"returncode": 0, "stdout": "", "stderr": ""})()
            vpk_tool = base / "vpk.exe"; vpk_tool.write_bytes(b"stub")  # pack_directory проверяет .exists()
            # vpk.exe вызывается в PackagingService.pack_directory - патчим там
            with patch("src.services.packaging_service.subprocess.run", side_effect=fake_run):
                with patch("src.services.packaging_service.ToolPaths.get_vpk_tool", return_value=vpk_tool):
                    result = MergeVPKService._create_vpk_from_directory(vpkroot, "out.vpk", export_folder=str(base))
                    self.assertTrue(result.endswith("out.vpk"))

    def test_create_vpk_from_directory_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            vpkroot = base / "vpkroot"
            vpkroot.mkdir()
            def fake_run(*args, **kwargs):
                return type("R", (), {"returncode": 1, "stdout": "bad", "stderr": "err"})()
            vpk_tool = base / "vpk.exe"; vpk_tool.write_bytes(b"stub")  # pack_directory проверяет .exists()
            # vpk.exe вызывается в PackagingService.pack_directory - патчим там
            with patch("src.services.packaging_service.subprocess.run", side_effect=fake_run):
                with patch("src.services.packaging_service.ToolPaths.get_vpk_tool", return_value=vpk_tool):
                    with self.assertRaises(VPKCreationError):
                        MergeVPKService._create_vpk_from_directory(vpkroot, "out.vpk", export_folder=str(base))

    def test_create_vpk_missing_tool_raises_friendly(self):
        # Нет ни бандла, ни vpk.exe из TF2 -> понятная RequiredFileMissingError
        # (а не сырой FileNotFoundError из subprocess). pre-flight в pack_directory
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            vpkroot = base / "vpkroot"
            vpkroot.mkdir()
            missing = base / "nope" / "vpk.exe"   # не существует
            with patch("src.services.packaging_service.ToolPaths.get_vpk_tool", return_value=missing):
                with self.assertRaises(RequiredFileMissingError):
                    MergeVPKService._create_vpk_from_directory(vpkroot, "out.vpk", export_folder=str(base))


if __name__ == "__main__":
    unittest.main()
