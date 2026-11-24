"""
Файлы игры, переписанные прелоадером прямо в архивах

Прелоадер не трогает каталог `*_dir.vpk`, и CRC оригинала остаётся там:
по нему подмена видна, и по нему же проверяется копия, которой её заменяем
"""

import zlib
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from src.services import game_integrity as gi

ORIGINAL = b"original pcf"
MODDED = b"modded pcf from a preloader"
CRC = zlib.crc32(ORIGINAL) & 0xFFFFFFFF


@pytest.fixture(autouse=True)
def _clean():
    gi.reset()
    yield
    gi.reset()


def _backup(root: Path, data: bytes = ORIGINAL) -> Path:
    backup = root / "Desktop" / "preloader" / "casual-preloader" / "backup"
    (backup / "particles").mkdir(parents=True)
    (backup / "particles" / "crit.pcf").write_bytes(data)
    return backup


def test_untouched_file_passes_as_is(tmp_path):
    with patch.object(gi, "sources", return_value=[]):
        assert gi.checked(ORIGINAL, "particles/crit.pcf", CRC) == ORIGINAL
    assert gi.summary() == {"modified": [], "restored": []}


def test_modded_file_is_replaced_by_the_verified_original(tmp_path):
    with patch.object(gi, "sources", return_value=[_backup(tmp_path)]):
        assert gi.checked(MODDED, "particles/crit.pcf", CRC) == ORIGINAL
    assert gi.summary() == {"modified": [], "restored": ["particles/crit.pcf"]}
    assert not gi.is_modified("particles/crit")


def test_installed_mode_gives_the_file_as_it_is_in_the_game(tmp_path):
    """Человек выбрал править установленный мод: оригинал не подставляем,
    но подмену всё равно запоминаем - по ней страница показывает выбор"""
    with patch.object(gi, "sources", return_value=[_backup(tmp_path)]):
        assert not gi.is_patched("particles/crit.pcf")
        with gi.as_installed():
            assert gi.checked(MODDED, "particles/crit.pcf", CRC) == MODDED
        assert gi.checked(MODDED, "particles/crit.pcf", CRC) == ORIGINAL
    assert gi.is_patched("Particles\\Crit.pcf")


def test_a_copy_with_the_wrong_crc_is_not_trusted(tmp_path):
    """В копии прелоадера мог оказаться и сам мод - на слово не верим"""
    with patch.object(gi, "sources", return_value=[_backup(tmp_path, MODDED)]):
        assert gi.checked(MODDED, "particles/crit.pcf", CRC) == MODDED
    assert gi.summary()["modified"] == ["particles/crit.pcf"]
    assert gi.is_modified("particles/crit")


def test_each_file_is_reported_once():
    calls = []
    gi.on_change(lambda: calls.append(1))
    with patch.object(gi, "sources", return_value=[]):
        gi.checked(MODDED, "Particles\\Crit.pcf", CRC)
        gi.checked(MODDED, "particles/crit.pcf", CRC)
    assert len(calls) == 1


def test_new_preloader_path_retries_files_without_an_original(tmp_path):
    """Прелоадер указали позже - подмену, у которой не было оригинала,
    надо проверить заново: теперь он может найтись"""
    with patch.object(gi, "sources", return_value=[]):
        gi.checked(MODDED, "particles/crit.pcf", CRC)
    assert gi.is_modified("particles/crit")
    gi.forget_sources()
    assert not gi.is_modified("particles/crit")


def test_only_game_archives_are_checked():
    assert gi.is_game_vpk("D:/TF2/tf/tf2_misc_dir.vpk")
    assert gi.is_game_vpk("hl2_textures_dir.vpk")
    assert not gi.is_game_vpk("D:/mods/claymore_mod.vpk")
    assert not gi.is_game_vpk("tf/custom/_casual_preloader_dir.vpk")


class _File:
    def __init__(self, data, crc):
        self._data, self.crc32, self._pos = data, crc, 0

    def tell(self):
        return self._pos

    def seek(self, pos):
        self._pos = pos

    def read(self, size=-1):
        part = self._data[self._pos:] if size < 0 else self._data[self._pos:self._pos + size]
        self._pos += len(part)
        return part

    def close(self):
        pass


def test_guard_checks_full_reads_of_a_game_archive(tmp_path):
    pak = SimpleNamespace(get_vpkfile_instance=lambda path, meta: _File(MODDED, CRC))
    with patch.object(gi, "sources", return_value=[_backup(tmp_path)]):
        gi.guard(pak, "tf2_misc_dir.vpk")
        assert pak.get_vpkfile_instance("particles/crit.pcf", None).read() == ORIGINAL
        # Заголовок читают частично - сверять там нечего
        assert pak.get_vpkfile_instance("particles/crit.pcf", None).read(6) == MODDED[:6]


def test_mod_archives_are_left_alone():
    pak = SimpleNamespace(get_vpkfile_instance=lambda path, meta: _File(MODDED, CRC))
    gi.guard(pak, "claymore_mod.vpk")
    assert pak.get_vpkfile_instance("particles/crit.pcf", None).read() == MODDED
