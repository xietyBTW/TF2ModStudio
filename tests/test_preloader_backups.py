"""
Где у прелоадера копии файлов игры - по тому, что указал человек

Указывают то, что привычно: файл запуска (RUNME.bat лежит на уровень выше
папки с копиями), саму папку или файл где-то в глубине. Раскладка меняется от
версии к версии - тогда копии ищутся обходом выбранной папки
"""

from pathlib import Path

from src.services import game_integrity as gi
from src.services import preloader_backups as pb


def _current_layout(root: Path) -> Path:
    """Как сейчас: preloader/RUNME.bat и preloader/casual-preloader/backup"""
    (root / "preloader").mkdir()
    (root / "preloader" / "RUNME.bat").write_text("@echo off")
    backup = root / "preloader" / "casual-preloader" / "backup"
    (backup / "particles").mkdir(parents=True)
    (backup / "particles" / "crit.pcf").write_bytes(b"pcf")
    (root / "preloader" / "casual-preloader" / "core").mkdir()
    (root / "preloader" / "casual-preloader" / "core" / "main.py").write_text("")
    return backup


def test_launch_file_leads_to_the_backup(tmp_path):
    backup = _current_layout(tmp_path)
    assert pb.find(str(tmp_path / "preloader" / "RUNME.bat")) == [backup]


def test_the_folder_and_a_file_deep_inside_work_too(tmp_path):
    backup = _current_layout(tmp_path)
    assert pb.find(str(tmp_path / "preloader")) == [backup]
    assert pb.find(str(tmp_path / "preloader" / "casual-preloader" / "core" / "main.py")) == [backup]


def test_new_layout_is_found_by_walking_the_folder(tmp_path):
    """Новая версия назвала копии иначе - находятся по содержимому"""
    vanilla = tmp_path / "tool" / "files" / "v2" / "vanilla"
    (vanilla / "materials" / "skybox").mkdir(parents=True)
    (vanilla / "materials" / "skybox" / "sky.vmt").write_text("x")
    assert pb.find(str(tmp_path / "tool")) == [vanilla]


def test_nothing_useful_gives_nothing(tmp_path):
    (tmp_path / "empty").mkdir()
    assert pb.find(str(tmp_path / "empty")) == []
    assert pb.find("") == []
    assert pb.find(str(tmp_path / "missing")) == []


def test_integrity_takes_sources_from_the_setting(tmp_path, monkeypatch):
    from src.config.app_config import AppConfig

    backup = _current_layout(tmp_path)
    monkeypatch.setattr(AppConfig, "load_config", staticmethod(
        lambda: {"preloader_path": str(tmp_path / "preloader" / "RUNME.bat")}))
    gi.reset()
    try:
        assert gi.sources() == [backup]
    finally:
        gi.reset()
