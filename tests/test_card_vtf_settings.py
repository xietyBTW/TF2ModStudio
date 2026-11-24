"""Свои настройки VTF карточки (шестерёнка) доходят до любого сборщика

Правило «свои поверх общих» одно (texture_overrides.vtf_settings,
BuildRequest.vtf_for). Раньше оно жило замыканием в сборке модели, и маски
шпиона, гирлянды и стили шапки собирались общими настройками молча"""

import re
from pathlib import Path
from types import SimpleNamespace

from src.data.player_characters import SPY_DISGUISE_MASKS
from src.data.texture_overrides import vtf_settings
from src.services.build_request import BuildRequest


def test_card_settings_over_global():
    assert vtf_settings(512, "DXT1", None, None) == ((512, 512), "DXT1", [], {})
    assert vtf_settings((512, 512), "DXT1", ["A"], {"x": 1},
                        {"size": [1024, 1024], "format": "BGRA8888"}) == (
        (1024, 1024), "BGRA8888", ["A"], {"x": 1})


def test_request_finds_the_card_and_the_main():
    r = BuildRequest(material_settings={"mask_scout": {"size": [1024, 1024]},
                                        "": {"format": "DXT5"}})
    assert r.vtf_for("mask_scout")[0] == (1024, 1024)
    assert r.vtf_for("other")[0] == r.size
    # Главная одноматериальной модели хранится под пустым ключом
    assert r.vtf_for("c_bat", "c_bat")[1] == "DXT5"


def test_spy_mask_uses_its_card_settings(tmp_path, monkeypatch):
    from src.services import spy_mask_build as smb

    seen = {}
    monkeypatch.setattr(smb.TextureService, "process_image",
                        staticmethod(lambda img, png, size: seen.setdefault(Path(png).stem, [size])))
    monkeypatch.setattr(smb.TextureService, "create_vtf",
                        staticmethod(lambda png, out, fmt, flags, opts: seen[Path(png).stem].append(fmt)))
    monkeypatch.setattr(smb.PackagingService, "create_vpk_file",
                        staticmethod(lambda *a, **k: "mod.vpk"))
    img = tmp_path / "mask.png"
    img.write_bytes(b"x")
    first = SPY_DISGUISE_MASKS[0][1]
    r = BuildRequest(material_settings={first: {"size": [1024, 1024], "format": "BGRA8888"}})
    ctx = SimpleNamespace(vpkroot_dir=tmp_path, cleanup=lambda **k: None)
    smb.build_spy_masks_vpk(ctx, None, r.size, r.format_type, [], {}, "m", str(tmp_path), "ru",
                            lambda name, who: str(img), "", False, False, {}, vtf_for=r.vtf_for)
    assert seen[first] == [(1024, 1024), "BGRA8888"]
    other = SPY_DISGUISE_MASKS[1][1]
    assert seen[other] == [r.size, r.format_type]


def test_no_private_copy_of_the_rule():
    """Новый сборщик берёт vtf_settings / vtf_for, а не собирает правило сам"""
    src = Path(__file__).resolve().parent.parent / "src"
    raw = re.compile(r"\beffective_settings\(")
    found = [str(p.relative_to(src)) for p in src.rglob("*.py")
             if p.name != "texture_overrides.py" and raw.search(p.read_text(encoding="utf-8"))]
    assert not found, found
