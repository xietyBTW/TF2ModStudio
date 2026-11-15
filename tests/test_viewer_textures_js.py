"""
Текстуры модели во вьювере (viewer_textures.js) через Node

Две вещи, которые Python не видит: память видеокарты отдаётся, когда текстура
стала ничьей, и повторная раздача не грузит картинку, которая уже на мешах

Тест пропускается, если node недоступен
"""

import json
import shutil
import subprocess
from pathlib import Path

import pytest

MODULE = Path("src/static/js/viewer_textures.js").resolve()

pytestmark = pytest.mark.skipif(
    shutil.which("node") is None or not MODULE.exists(),
    reason="node недоступен или viewer_textures.js не найден")

# Модель: два меша предмета и гирлянда, у каждой текстуры счётчик dispose
SCENE = """
const tex = (url) => ({ userData: { url }, freed: 0, dispose() { this.freed++; } });
const geo = () => ({ freed: 0, dispose() { this.freed++; } });
const mesh = (name, map) => ({ isMesh: true, name, geometry: geo(),
                               material: { name, map } });
const model = (...meshes) => ({ meshes, traverse(fn) { meshes.forEach(fn); } });
const V = '/file?path=a.png&v=1';
"""


def _run(body: str) -> dict:
    script = f"""
import {{ mapsOf, freeObject, retireMaps, alreadyOn }} from {MODULE.as_uri()!r};
{SCENE}
const out = (() => {{ {body} }})();
console.log(JSON.stringify(out));
"""
    proc = subprocess.run(
        ["node", "--input-type=module", "-e", script],
        capture_output=True, text=True, timeout=60)
    assert proc.returncode == 0, proc.stderr
    return json.loads(proc.stdout.strip().splitlines()[-1])


def test_dropped_model_frees_geometry_and_textures_once():
    out = _run("""
        const shared = tex(V), lamp = tex('lamp');
        const a = mesh('a', shared), b = mesh('b', shared), deco = mesh('deco:x', lamp);
        freeObject(model(a, b, deco), t => t === lamp);
        return { shared: shared.freed, lamp: lamp.freed,
                 geo: [a, b, deco].map(m => m.geometry.freed) };""")
    assert out == {"shared": 1, "lamp": 0, "geo": [1, 1, 1]}


def test_texture_is_retired_only_when_nobody_holds_it():
    out = _run("""
        const onMesh = tex('m'), inStock = tex('s'), orphan = tex('o'), lamp = tex('l');
        retireMaps([onMesh, inStock, orphan, lamp, null], model(mesh('a', onMesh)),
                   [inStock], t => t === lamp);
        return [onMesh, inStock, orphan, lamp].map(t => t.freed);""")
    assert out == [0, 0, 1, 0]


def test_retire_without_a_model():
    assert _run("const t = tex('o'); retireMaps([t], null); return t.freed;") == 1


def test_same_versioned_url_on_every_picked_mesh_is_skipped():
    out = _run("""
        const t = tex(V);
        const m = model(mesh('a', t), mesh('b', t), mesh('other', tex('x')));
        const pick = c => c.name !== 'other';
        return { same: alreadyOn(m, V, pick) === t,
                 otherUrl: alreadyOn(m, V + '2', pick),
                 all: alreadyOn(m, V, () => true),
                 nobody: alreadyOn(m, V, () => false),
                 noModel: alreadyOn(null, V, pick) };""")
    assert out == {"same": True, "otherUrl": None, "all": None,
                   "nobody": None, "noModel": None}


def test_url_without_version_is_always_loaded():
    out = _run("""
        const plain = '/file?path=a.png', t = tex(plain);
        return alreadyOn(model(mesh('a', t)), plain, () => true);""")
    assert out is None


def test_decor_and_bare_meshes_do_not_count():
    out = _run("""
        const t = tex(V);
        const m = model(mesh('a', t), mesh('deco:x', tex('lamp')), mesh('b', null));
        const aside = name => name.startsWith('deco:');
        return { withBare: alreadyOn(m, V, () => true, aside),
                 itemOnly: alreadyOn(m, V, c => c.name === 'a', aside) === t };""")
    assert out == {"withBare": None, "itemOnly": True}
