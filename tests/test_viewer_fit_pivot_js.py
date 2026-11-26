"""
Опора гизмо подгонки (viewer_fit_pivot.js) через Node с настоящим three.js

У модели «из интернета» ноль бывает далеко от геометрии: гизмо, стоявшее в
нуле, висело в воздухе рядом с катаной. Проверяется, что опора встаёт в центр
модели, движение опоры оставляет центр под ней, а числа подгонки переводятся
туда и обратно без потерь

Тест пропускается, если node недоступен
"""

import json
import shutil
import subprocess
from pathlib import Path

import pytest

MODULE = Path("src/static/js/viewer_fit_pivot.js").resolve()
THREE = Path("src/static/js/three.module.js").resolve()

pytestmark = pytest.mark.skipif(
    shutil.which("node") is None or not MODULE.exists() or not THREE.exists(),
    reason="node недоступен или модули не найдены")

SCRIPT = """
const THREE = await import(%(three)s);
const { createFitPivot, fitPose, fitFromNode } = await import(%(module)s);

const parent = new THREE.Group();
const node = new THREE.Group();
parent.add(node);
// Брусок далеко от нуля модели: x от 60 до 140
const mesh = new THREE.Mesh(new THREE.BoxGeometry(80, 4, 4));
mesh.position.set(100, 0, 0);
node.add(mesh);

const pivot = createFitPivot(THREE);
node.scale.setScalar(0.5);
pivot.sync(node);
const synced = pivot.object.position.toArray();

// Тянем опору: модель едет так, что центр остаётся под ней
pivot.object.position.set(10, 20, 30);
pivot.apply(node);
node.updateMatrixWorld(true);
const center = pivot.centerWorld(node).toArray();

// Числа подгонки туда и обратно
const pose = fitPose(THREE, 1.5, [10, 20, 30], [1, 2, 3]);
const probe = new THREE.Group();
probe.quaternion.copy(pose.quat); probe.scale.setScalar(pose.scale); probe.position.copy(pose.pos);
const back = fitFromNode(THREE, probe);

console.log(JSON.stringify({ synced, center, back }));
"""


def _run():
    script = SCRIPT % {"three": json.dumps(THREE.as_uri()), "module": json.dumps(MODULE.as_uri())}
    done = subprocess.run(["node", "--input-type=module", "-e", script],
                          capture_output=True, text=True, timeout=60)
    assert done.returncode == 0, done.stderr
    return json.loads(done.stdout.strip().splitlines()[-1])


def _close(a, b, tol=1e-3):
    return all(abs(x - y) < tol for x, y in zip(a, b))


def test_pivot_sits_on_the_model_not_on_its_origin():
    assert _close(_run()["synced"], [50, 0, 0])      # центр 100 при масштабе 0,5


def test_dragging_the_pivot_keeps_the_center_under_it():
    assert _close(_run()["center"], [10, 20, 30])


def test_fit_numbers_survive_the_round_trip():
    back = _run()["back"]
    assert back["scale"] == 1.5
    assert _close(back["rotate"], [10, 20, 30], 0.11)
    assert _close(back["offset"], [1, 2, 3], 0.11)


LAID_SCRIPT = """
const THREE = await import(%(three)s);
const { vectorInParent, quatInParent } = await import(%(module)s);
// Модель предмета положена набок (viewer_lay.js) и ужата, узел подгонки в ней
const model = new THREE.Group();
model.quaternion.setFromAxisAngle(new THREE.Vector3(0, 0, 1), Math.PI / 2);
model.scale.setScalar(0.5);
const node = new THREE.Group();
model.add(node);
model.updateMatrixWorld(true);

// Сдвиг мыши на 1 вправо по экрану: узел должен уехать вправо и в мире
node.position.add(vectorInParent(THREE, model, new THREE.Vector3(1, 0, 0)));
model.updateMatrixWorld(true);
const moved = node.getWorldPosition(new THREE.Vector3()).toArray();

// Поворот на 90 вокруг мировой Y: мировой поворот узла - ровно он
const q = new THREE.Quaternion().setFromAxisAngle(new THREE.Vector3(0, 1, 0), Math.PI / 2);
node.quaternion.copy(quatInParent(THREE, model, q));
model.updateMatrixWorld(true);
const wq = node.getWorldQuaternion(new THREE.Quaternion());
const expect = q.clone().multiply(model.quaternion);
console.log(JSON.stringify({ moved, angle: wq.angleTo(expect) }));
"""


def test_fit_moves_follow_the_screen_on_a_laid_model():
    """Своя модель и гирлянда двигаются мышью за экраном, хотя модель
    предмета во вьювере повёрнута"""
    script = LAID_SCRIPT % {"three": json.dumps(THREE.as_uri()), "module": json.dumps(MODULE.as_uri())}
    proc = subprocess.run(["node", "--input-type=module", "-e", script],
                          capture_output=True, text=True, timeout=60)
    assert proc.returncode == 0, proc.stderr
    out = json.loads(proc.stdout.strip().splitlines()[-1])
    assert [round(v, 6) for v in out["moved"]] == [1, 0, 0]
    assert out["angle"] < 1e-6
