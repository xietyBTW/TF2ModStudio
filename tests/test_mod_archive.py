"""Мод из ZIP или папки - в VPK библиотеки; чужой архив распаковывается с опаской"""

import zipfile
from pathlib import Path

import pytest
import vpk

from src.services import mod_archive, mod_library_service


@pytest.fixture
def library(tmp_path, monkeypatch):
    """Библиотека во временной папке, vpk.exe - упаковкой библиотеки vpk"""
    lib = tmp_path / "library"
    monkeypatch.setattr(mod_library_service, "LIBRARY_DIR", lib)

    def pack(folder, filename, export_folder="export", language="en"):
        out = Path(export_folder) / filename
        out.parent.mkdir(parents=True, exist_ok=True)
        vpk.new(str(folder)).save(str(out))
        return str(out)

    from src.services.packaging_service import PackagingService
    monkeypatch.setattr(PackagingService, "pack_directory", staticmethod(pack))
    return lib


def _files(root, names):
    for rel in names:
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        (root / rel).write_bytes(b"data " + rel.encode())


def _zip(path, members):
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, data in members.items():
            zf.writestr(name, data)
    return path


def test_vpk_inside_a_zip_goes_to_the_library(tmp_path, library):
    mod = tmp_path / "src"
    _files(mod, ["materials/models/x.vtf"])
    vpk.new(str(mod)).save(str(tmp_path / "skin.vpk"))
    archive = _zip(tmp_path / "pack.zip",
                   {"readme.txt": "hi", "custom/skin.vpk": (tmp_path / "skin.vpk").read_bytes()})
    made = mod_archive.import_mod(str(archive))
    assert [p.name for p in made] == ["skin.vpk"]
    assert made[0].parent == library


def test_loose_mod_folders_become_one_vpk_each(tmp_path, library):
    # Сборник: две папки как в tf/custom, внутри - materials и models
    archive = _zip(tmp_path / "set.zip", {
        "set/red_scatter/materials/models/a.vtf": "a",
        "set/red_scatter/models/a.mdl": "m",
        "set/blue_bat/materials/models/b.vtf": "b",
    })
    made = mod_archive.import_mod(str(archive))
    assert sorted(p.name for p in made) == ["blue_bat.vpk", "red_scatter.vpk"]
    pak = vpk.open(str(library / "red_scatter.vpk"))
    assert sorted(pak) == ["materials/models/a.vtf", "models/a.mdl"]


def test_a_folder_is_packed_without_writing_next_to_it(tmp_path, library):
    custom = tmp_path / "tf" / "custom" / "mymod"
    _files(custom, ["materials/models/x.vtf"])
    made = mod_archive.import_mod(str(custom))
    assert [p.name for p in made] == ["mymod.vpk"]
    assert sorted(p.name for p in custom.parent.iterdir()) == ["mymod"]


def test_multi_chunk_vpk_is_repacked_into_one_file(tmp_path, library):
    src = tmp_path / "big"
    _files(src, ["materials/models/x.vtf", "models/x.mdl"])
    folder = tmp_path / "dl"
    folder.mkdir()
    # Многотомный открывается своим _dir.vpk, тома читает сама библиотека vpk
    # (создавать их она не умеет); здесь важна пересборка в один файл
    vpk.new(str(src)).save(str(folder / "big_dir.vpk"))
    (folder / "big_000.vpk").write_bytes(b"")
    made = mod_archive.import_mod(str(folder))
    assert [p.name for p in made] == ["big.vpk"]
    assert sorted(vpk.open(str(made[0]))) == ["materials/models/x.vtf", "models/x.mdl"]


def test_path_leaving_the_folder_is_refused(tmp_path, library):
    archive = _zip(tmp_path / "evil.zip", {"../../outside.txt": "x",
                                           "materials/a.vtf": "a"})
    with pytest.raises(mod_archive.ModArchiveError):
        mod_archive.import_mod(str(archive))
    assert not (tmp_path / "outside.txt").exists()


def test_zip_bomb_is_refused(tmp_path, library):
    archive = _zip(tmp_path / "bomb.zip", {"materials/a.vtf": b"\0" * (20 * 1024 ** 2)})
    with pytest.raises(mod_archive.ModArchiveError):
        mod_archive.import_mod(str(archive))


def test_archive_without_a_mod_is_refused(tmp_path, library):
    archive = _zip(tmp_path / "pics.zip", {"photos/cat.jpg": "x"})
    with pytest.raises(mod_archive.ModArchiveError):
        mod_archive.import_mod(str(archive))
