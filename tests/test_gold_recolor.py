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

    out = np.asarray(Image.open(recolor(str(tmp_path / 'base.png'),
                                        str(tmp_path / 'gold.png'),
                                        str(tmp_path / 'out.png'))))
    dark, light = out[0, 0], out[7, 7]
    assert dark[0] > dark[2] and light[0] > light[2]      # золото, а не синее
    assert light[0] > dark[0] and light[3] > dark[3]      # рисунок и блеск по яркости
    assert (out[:4] == dark).all() and (out[4:] == light).all()   # заливка без шума
