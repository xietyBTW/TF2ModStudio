"""Перекраска под австралий: палитра золота этого оружия, рисунок цел"""

import numpy as np
from PIL import Image

from src.services.gold_recolor import recolor


def test_recolor_follows_the_gold_and_keeps_the_picture(tmp_path):
    gold = np.zeros((16, 16, 4), np.uint8)
    gold[..., 0] = np.linspace(60, 250, 16)[None, :]      # тёмное -> светлое золото
    gold[..., 1] = np.linspace(40, 200, 16)[None, :]
    gold[..., 2] = 10
    gold[..., 3] = np.linspace(20, 240, 16)[None, :]      # блеск ярче на светлом
    Image.fromarray(gold, 'RGBA').save(tmp_path / 'gold.png')
    base = np.zeros((8, 8, 4), np.uint8)
    base[:4] = (30, 30, 200, 255)                         # тёмная синяя половина
    base[4:] = (220, 220, 220, 255)                       # светлая серая
    Image.fromarray(base, 'RGBA').save(tmp_path / 'base.png')

    # Своя модель: развёртка чужая, маска блеска - по яркости
    out = np.asarray(Image.open(recolor(str(tmp_path / 'base.png'),
                                        str(tmp_path / 'gold.png'),
                                        str(tmp_path / 'out.png'),
                                        keep_gold_alpha=False)))
    dark, light = out[0, 0], out[7, 7]
    assert dark[0] > dark[2] and light[0] > light[2]      # золото, а не синее
    assert light[0] > dark[0] and light[3] > dark[3]      # рисунок и блеск по яркости
    assert (out[:4] == dark).all() and (out[4:] == light).all()   # заливка без шума


def test_shine_mask_comes_from_the_game_gold(tmp_path):
    """Маска блеска Valve нарисована по деталям: по яркости она выходила
    другой, и золото там темнело"""
    gold = np.full((8, 8, 4), 120, np.uint8)
    gold[..., 3] = 0
    gold[:, 4:, 3] = 255                                   # блестит правая половина
    Image.fromarray(gold, 'RGBA').save(tmp_path / 'gold.png')
    base = np.zeros((16, 16, 4), np.uint8)
    base[..., :3] = np.linspace(0, 255, 16)[:, None, None]  # яркость по вертикали
    base[..., 3] = 255
    Image.fromarray(base, 'RGBA').save(tmp_path / 'base.png')

    out = np.asarray(Image.open(recolor(str(tmp_path / 'base.png'),
                                        str(tmp_path / 'gold.png'),
                                        str(tmp_path / 'out.png'))))
    assert out.shape[:2] == (16, 16)
    assert (out[:, :6, 3] == 0).all() and (out[:, 10:, 3] == 255).all()


def test_what_gets_gilded(monkeypatch):
    """Своя картинка на карточке австралия, иначе своя обычная; нетронутое
    и прошлый результат перекраски золотить нечего"""
    from types import SimpleNamespace

    from src.app.materials_editor import MaterialsEditor
    from src.domain.preview import variant_card

    on_card = {"path": None}
    regular = {"path": "game.png"}
    t = SimpleNamespace(
        active_team="red", australium_mat_name="gun_gold",
        variant_game=lambda team: "gold.png", stable_main=lambda: "gun",
        storage_main_key=lambda: "gun",
        shown_at=lambda mat, row, team: regular["path"],
        game_base=lambda mat, team: "game.png")
    monkeypatch.setattr(variant_card, "shown", lambda t, team: on_card["path"] or "gold.png")
    monkeypatch.setattr(variant_card, "choice",
                        lambda t, team: "own" if on_card["path"] else "game")
    editor = MaterialsEditor(SimpleNamespace(preview=SimpleNamespace(textures=t, custom_vpk_mode=False),
                                             _custom_geometry=lambda: False))

    assert editor._gild_source() is None                          # всё игровое
    on_card["path"] = "C:/mine.png"
    assert editor._gild_source()[1] == "C:/mine.png"              # своя на золоте
    on_card["path"] = "C:/tmp/tf2sg_gold_x.png"
    assert editor._gild_source() is None                          # уже перекрашено
    regular["path"] = "C:/my_regular.png"
    assert editor._gild_source()[1] == "C:/my_regular.png"        # обычная поменялась
