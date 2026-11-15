"""
Запас превью на диске: готовые OBJ и PNG переживают перезапуск

Проверяется сам запас (запись заменой, уборка по давности) и оба его
потребителя: после «перезапуска» (запас в памяти пуст) модель и текстура
берутся с диска без разбора SMD и без декодера VTF
"""

import os
from pathlib import Path
from unittest.mock import patch

import pytest

from src.services import preview_disk_cache as cache
from src.services import smd_to_obj_service, vtf_preview_service
from src.services.smd_to_obj_service import SmdToObjService

SMD = """version 1
nodes
0 "root" -1
end
skeleton
time 0
0 0 0 0 0 0 0
end
triangles
gun
0 0 0 0 0 0 1 0 0
0 1 0 0 0 0 1 1 0
0 0 1 0 0 0 1 0 1
end
"""


@pytest.fixture
def disk(tmp_path, monkeypatch):
    monkeypatch.setattr(cache, "DIR", tmp_path / "preview")
    monkeypatch.setattr(cache, "_written", 0)
    return tmp_path / "preview"


def test_put_then_get(disk):
    key = b"\x01\x02"
    assert cache.get("png", key) is None
    cache.put("png", key, b"data")
    assert cache.get("png", key) == b"data"
    assert cache.get("obj", key) is None          # виды не смешиваются
    assert not list(disk.rglob("*.tmp"))


def test_disabled_cache_keeps_nothing(monkeypatch):
    monkeypatch.setattr(cache, "DIR", None)
    cache.put("png", b"k", b"data")
    assert cache.get("png", b"k") is None
    assert cache.size_mb() == 0 and cache.clear() == 0 and cache.trim() == 0


def test_new_version_does_not_see_old_records(disk, monkeypatch):
    cache.put("png", b"k", b"old")
    monkeypatch.setattr(cache, "VERSION", cache.VERSION + 1)
    assert cache.get("png", b"k") is None


def test_trim_removes_the_longest_unused(disk):
    for i in range(4):
        cache.put("png", bytes([i]), b"x" * 1024)
        path = cache._path("png", bytes([i]))
        os.utime(path, (1000 + i, 1000 + i))
    cache.get("png", bytes([0]))                  # прочитали - снова свежая
    removed = cache.trim(max_mb=3 * 1024 / (1024 * 1024))
    assert removed == 2
    assert cache.get("png", bytes([0])) is not None
    assert cache.get("png", bytes([1])) is None and cache.get("png", bytes([2])) is None
    assert cache.get("png", bytes([3])) is not None


def test_trim_within_limit_touches_nothing(disk):
    cache.put("png", b"k", b"x" * 1024)
    assert cache.trim(max_mb=1) == 0
    assert cache.get("png", b"k") is not None


def test_clear_and_size(disk):
    cache.put("png", b"a", b"x" * 2048)
    cache.put("obj", b"b", b"x" * 2048)
    assert cache.size_mb() == pytest.approx(4096 / (1024 * 1024))
    assert cache.clear() == 2
    assert cache.size_mb() == 0


def test_writing_enough_starts_a_sweep(disk, monkeypatch):
    monkeypatch.setattr(cache, "_SWEEP_EVERY", 10)
    swept = []
    monkeypatch.setattr(cache, "trim", lambda *a, **k: swept.append(1))
    cache.put("png", b"a", b"12345")
    assert not swept
    cache.put("png", b"b", b"123456")
    for thread in list(cache.threading.enumerate()):
        if thread.name == "preview-cache-trim":
            thread.join(5)
    assert swept == [1]


# PNG текстур

def test_png_frames_roundtrip():
    frames = [b"first", b"second!", b"3"]
    assert vtf_preview_service._unpack(vtf_preview_service._pack(frames)) == frames


@pytest.mark.parametrize("blob", [None, b"", b"\x05\x00\x00\x00ab", b"\x01\x00",
                                  b"\x00\x00\x00\x00"])
def test_broken_png_record_is_a_miss(blob):
    assert vtf_preview_service._unpack(blob) == []


def test_texture_comes_from_disk_after_restart(disk, tmp_path):
    rgba = bytes([10, 20, 30, 255]) * 16
    with patch("src.services.vtflib_wrapper.VTFLib.read_vtf_all_frames",
               return_value=([rgba], 4, 4)) as decode:
        first = vtf_preview_service._decode_pngs(b"vtf-bytes", str(tmp_path), "a", False)
        vtf_preview_service.clear_png_cache()     # «перезапуск»
        second = vtf_preview_service._decode_pngs(b"vtf-bytes", str(tmp_path), "a", False)
        other = vtf_preview_service._decode_pngs(b"another", str(tmp_path), "b", False)
    assert first == second and first[0].startswith(b"\x89PNG")
    assert other == first
    assert decode.call_count == 2                 # второй раз декодер не звали


# OBJ моделей

def test_obj_record_roundtrip():
    made = (b"v 1 2 3\n", b"newmtl gun\n", ("gun", "скоба"))
    assert smd_to_obj_service._from_blob(smd_to_obj_service._to_blob(made)) == made


@pytest.mark.parametrize("blob", [None, b"", b"not json\nbody", b'{"names": []}\nbody',
                                  b'{"names": ["a"], "obj": 9, "mtl": 0}\nshort'])
def test_broken_obj_record_is_a_miss(blob):
    assert smd_to_obj_service._from_blob(blob) is None


def test_model_comes_from_disk_after_restart(disk, tmp_path, monkeypatch):
    monkeypatch.setattr(smd_to_obj_service, "_keeps_on_disk", lambda parts: True)
    smd = tmp_path / "gun.smd"
    smd.write_text(SMD)
    (tmp_path / "a").mkdir()
    ok, names = SmdToObjService.convert(str(smd), str(tmp_path / "a" / "model.obj"))
    assert ok and names == ["gun"]
    first = (tmp_path / "a" / "model.obj").read_bytes()

    smd_to_obj_service._recent.clear()            # «перезапуск»
    with patch.object(SmdToObjService, "_convert_parts") as convert:
        ok, names = SmdToObjService.convert(str(smd), str(tmp_path / "b" / "model.obj"))
    convert.assert_not_called()
    assert ok and names == ["gun"]
    assert (tmp_path / "b" / "model.obj").read_bytes() == first
    assert (tmp_path / "b" / "model.mtl").is_file()


def test_changed_model_is_converted_again(disk, tmp_path, monkeypatch):
    monkeypatch.setattr(smd_to_obj_service, "_keeps_on_disk", lambda parts: True)
    smd = tmp_path / "gun.smd"
    smd.write_text(SMD)
    SmdToObjService.convert(str(smd), str(tmp_path / "model.obj"))
    smd_to_obj_service._recent.clear()
    smd.write_text(SMD.replace("gun", "blade"))
    os.utime(smd, ns=(5, 5))
    ok, names = SmdToObjService.convert(str(smd), str(tmp_path / "model.obj"))
    assert ok and names == ["blade"]


def test_temporary_models_stay_off_disk(tmp_path, monkeypatch):
    monkeypatch.setattr(smd_to_obj_service.tempfile, "gettempdir", lambda: str(tmp_path))
    part = smd_to_obj_service.MeshPart
    assert not smd_to_obj_service._keeps_on_disk([part(str(tmp_path / "x" / "a.smd"))])
    assert not smd_to_obj_service._keeps_on_disk(
        [part(str(Path("C:/cache/a.smd")), extra_smd_paths=[str(tmp_path / "b.smd")])])
    assert smd_to_obj_service._keeps_on_disk([part(str(Path("C:/cache/a.smd")))])
