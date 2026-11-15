"""
Слой огня во вьювере (viewer_fire.js) через Node

Числа взяты из игры: сила огня по прокси BurnLevel (вспышка 0,3 с, угасание к
десятой секунде) и порог из шейдера (TextureCombinePostLighting, режим 6).
Превью обязано повторять их, иначе горящий выглядит не так, как в игре

Тест пропускается, если node недоступен
"""

import json
import shutil
import subprocess
from pathlib import Path

import pytest

MODULE = Path("src/static/js/viewer_fire.js").resolve()

pytestmark = pytest.mark.skipif(
    shutil.which("node") is None or not MODULE.exists(),
    reason="node недоступен или viewer_fire.js не найден")


def _run(body: str):
    script = f"""
import {{ atlasCells, frameAt, burnLevel, thresholdFade, BURN_SECONDS, BURN_PEAK }}
  from {MODULE.as_uri()!r};
const out = (() => {{ {body} }})();
console.log(JSON.stringify(out));
"""
    proc = subprocess.run(
        ["node", "--input-type=module", "-e", script],
        capture_output=True, text=True, timeout=60)
    assert proc.returncode == 0, proc.stderr
    return json.loads(proc.stdout.strip().splitlines()[-1])


def test_atlas_is_cut_row_by_row():
    """121 кадр игры лежит сеткой 11x11 по 64 точки"""
    cells = _run("return atlasCells(704, 704, 11, 11, 121);")
    assert len(cells) == 121
    assert cells[0] == [0, 0, 64, 64]
    assert cells[10] == [640, 0, 64, 64]
    assert cells[11] == [0, 64, 64, 64]
    assert cells[120] == [640, 640, 64, 64]


def test_atlas_ignores_empty_tail_cells():
    """Кадров меньше, чем клеток: хвост листа пуст и в анимацию не идёт"""
    assert len(_run("return atlasCells(192, 128, 3, 2, 5);")) == 5
    assert len(_run("return atlasCells(192, 128, 3, 2, 99);")) == 6


def test_frames_loop_like_the_game_proxy():
    out = _run("""return [frameAt(0, 30, 121), frameAt(1, 30, 121),
                          frameAt(4.04, 30, 121), frameAt(5, 0, 1), frameAt(3, 30, 0)];""")
    assert out == [0, 30, 0, 0, 0]


def test_burn_level_flares_then_fades():
    out = _run("""return [burnLevel(0), burnLevel(BURN_PEAK / 2), burnLevel(BURN_PEAK),
                          burnLevel((BURN_SECONDS + BURN_PEAK) / 2),
                          burnLevel(BURN_SECONDS - 0.001), burnLevel(BURN_SECONDS)];""")
    assert out[0] == 0
    assert out[1] == pytest.approx(0.5)
    assert out[2] == pytest.approx(1.0)
    assert out[3] == pytest.approx(0.5)
    assert out[4] == pytest.approx(0.0, abs=1e-3)
    assert out[5] == 0, "десять секунд прошло - солдата поджигают заново"


def test_full_burn_adds_the_texture_as_is():
    out = _run("return [0, 0.25, 0.5, 1].map(d => thresholdFade(d, 1));")
    assert out == [0, 0.25, 0.5, 1]


def test_fading_fire_keeps_only_bright_spots():
    """На половине силы тёмная половина текстуры уже не горит"""
    out = _run("return [0.25, 0.5, 0.75, 1].map(d => thresholdFade(d, 0.5));")
    assert out == pytest.approx([0, 0, 0.5, 1])
    weak = _run("return [0.5, 0.75, 1].map(d => thresholdFade(d, 0.25));")
    assert weak == pytest.approx([0, 0.25, 0.5])


def test_no_fire_at_zero_level():
    assert _run("return [0, 0.5, 1].map(d => thresholdFade(d, 0));") == [0, 0, 0]
