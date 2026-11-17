"""
Анимации текстур во вьювере (viewer_anims.js) через Node

Гифки на разных материалах крутятся одновременно и друг друга не гасят, а
анимация на все меши с именными не живёт

Тест пропускается, если node недоступен
"""

import json
import shutil
import subprocess
from pathlib import Path

import pytest

MODULE = Path("src/static/js/viewer_anims.js").resolve()

pytestmark = pytest.mark.skipif(
    shutil.which("node") is None or not MODULE.exists(),
    reason="node недоступен или viewer_anims.js не найден")

# Таймеры ручные: tick(имя) двигает анимацию на кадр
SCENE = """
const applied = [], retired = [], timers = new Map();
let nextId = 1;
const anims = createAnims({
  apply: (name, tex) => applied.push(name + ':' + tex),
  retire: (frames) => retired.push(...frames),
  every: (fn, ms) => { timers.set(nextId, { fn, ms }); return nextId++; },
  cancel: (id) => timers.delete(id),
});
const run = (name, frames, fps = 10, key = frames.join()) => {
  const anim = anims.claim(name, key, frames);
  if (anim) anims.start(name, anim, fps);
  return anim;
};
const tick = () => [...timers.values()].forEach(t => t.fn());
"""


def _run(body: str):
    script = f"""
import {{ createAnims }} from {MODULE.as_uri()!r};
{SCENE}
const out = (() => {{ {body} }})();
console.log(JSON.stringify(out));
"""
    proc = subprocess.run(
        ["node", "--input-type=module", "-e", script],
        capture_output=True, text=True, timeout=60)
    assert proc.returncode == 0, proc.stderr
    return json.loads(proc.stdout.strip().splitlines()[-1])


def test_two_materials_play_side_by_side():
    out = _run("""
        run('a', ['a0', 'a1']); run('b', ['b0', 'b1', 'b2'], 20);
        tick(); tick(); tick();
        return { applied, retired, ms: [...timers.values()].map(t => t.ms),
                 kept: anims.frames() };""")
    assert out["applied"] == ["a:a0", "b:b0", "a:a1", "b:b1", "a:a0", "b:b2"]
    assert out["retired"] == []
    assert out["ms"] == [100, 50]
    assert out["kept"] == ["a0", "a1", "b0", "b1", "b2"]


def test_the_same_animation_is_not_restarted():
    out = _run("""
        const first = run('a', ['a0', 'a1']);
        tick();
        const again = run('a', ['a0', 'a1']);
        tick();
        return { again, applied, timers: timers.size, owns: anims.owns('a', first) };""")
    assert out == {"again": None, "applied": ["a:a0", "a:a1"], "timers": 1, "owns": True}


def test_stopping_one_leaves_the_other_and_frees_only_its_frames():
    out = _run("""
        run('a', ['a0', 'a1']); run('b', ['b0', 'b1']);
        anims.stop('a');
        tick();
        return { applied, retired, covers: [anims.covers('a'), anims.covers('b')] };""")
    assert out == {"applied": ["b:b0"], "retired": ["a0", "a1"], "covers": [False, True]}


def test_a_new_gif_on_the_same_material_replaces_the_old_one():
    out = _run("""
        const old = run('a', ['a0', 'a1']);
        run('a', ['n0', 'n1']);
        tick();
        return { applied, retired, timers: timers.size, stale: anims.owns('a', old) };""")
    assert out == {"applied": ["a:n0"], "retired": ["a0", "a1"], "timers": 1, "stale": False}


def test_the_whole_model_animation_does_not_live_with_named_ones():
    out = _run("""
        run('a', ['a0', 'a1']); run('b', ['b0', 'b1']);
        run('', ['g0', 'g1']);
        const whole = { timers: timers.size, retired: [...retired], covers: anims.covers('zzz') };
        run('a', ['a0', 'a1']);
        tick();
        return { whole, applied, retired };""")
    assert out["whole"] == {"timers": 1, "retired": ["a0", "a1", "b0", "b1"], "covers": True}
    assert out["applied"] == ["a:a0"]
    assert out["retired"][-2:] == ["g0", "g1"]


def test_frames_that_arrive_after_a_stop_do_not_start_anything():
    out = _run("""
        const frames = [null, null];
        const anim = anims.claim('a', 'k', frames);
        frames[0] = 'a0';
        anims.stopAll();
        anims.start('a', anim, 10);
        return { timers: timers.size, retired, owns: anims.owns('a', anim) };""")
    assert out == {"timers": 0, "retired": ["a0", None], "owns": False}
