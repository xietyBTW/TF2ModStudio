"""
Поза оружия на обложке (viewer_item_pose.js) через Node

Формы синтетические, но с тем, по чему модуль решает: остриё тоньше рукояти,
рукоять торчит вбок одна. Длинная ось нарочно наискось к осям сцены - так
лежат модели, прикреплённые к кости руки

Тест пропускается, если node недоступен
"""

import json
import shutil
import subprocess
from pathlib import Path

import pytest

MODULE = Path("src/static/js/viewer_item_pose.js").resolve()

pytestmark = pytest.mark.skipif(
    shutil.which("node") is None or not MODULE.exists(),
    reason="node недоступен или viewer_item_pose.js не найден")

HELPERS = """
const dot = (a, b) => a[0] * b[0] + a[1] * b[1] + a[2] * b[2];
const norm = (a) => { const l = Math.hypot(...a); return a.map((v) => v / l); };
// Поворот точек в базис (u, v, w): модель лежит наискось
const place = (pts, u, v, w) => pts.flatMap(([x, y, z]) =>
  [0, 1, 2].map((k) => x * u[k] + y * v[k] + z * w[k]));
const U = norm([1, 2, -1]);
const V = norm([1, 0, 1]);
const W = [U[1] * V[2] - U[2] * V[1], U[2] * V[0] - U[0] * V[2], U[0] * V[1] - U[1] * V[0]];
"""


def _run(body: str):
    script = f"""
import {{ itemPose, eigenSym3 }} from {MODULE.as_uri()!r};
{HELPERS}
const out = (() => {{ {body} }})();
console.log(JSON.stringify(out));
"""
    proc = subprocess.run(
        ["node", "--input-type=module", "-e", script],
        capture_output=True, text=True, timeout=60)
    assert proc.returncode == 0, proc.stderr
    return json.loads(proc.stdout.strip().splitlines()[-1])


def test_blade_tip_goes_left():
    """Кунай: толстое кольцо рукояти с одного конца, остриё - с другого"""
    out = _run("""
      const pts = [];
      for (let t = 0; t <= 10; t += 0.05) {
        const r = t < 2 ? 1.2 : 0.6 * (10 - t) / 8;
        for (let a = 0; a < 6.28; a += 0.5) pts.push([t, r * Math.cos(a), 0.3 * r * Math.sin(a)]);
      }
      const pose = itemPose(place(pts, U, V, W));
      // Остриё на t = 10: от острия к рукояти - это -U, и это право экрана
      return { right: dot(pose.right, U) };
    """)
    assert out["right"] < -0.99


def test_sword_tip_goes_left_despite_hooks_near_it():
    """Клеймор из мода: у острия торчат петли, шире гарды. Решает сам кончик"""
    out = _run("""
      const pts = [];
      for (let t = 0; t <= 10; t += 0.02) {
        // навершие, рукоять, гарда, клинок до острия
        const h = t < 0.4 ? 0.4 : t < 1.4 ? 0.15 : t < 1.6 ? 1.5 : 0.4 * (10 - t) / 8.4;
        for (let k = -1; k <= 1; k += 0.25) pts.push([t, h * k, 0.05 * k]);
      }
      // Петли выше гарды: конец с остриём в целом шире конца с рукоятью
      for (const at of [6.5, 7.5, 8.5]) for (let y = 0; y <= 3.5; y += 0.05) pts.push([at, y, 0]);
      const pose = itemPose(place(pts, U, V, W));
      return { right: dot(pose.right, U) };
    """)
    # Здесь проверяется сторона острия; петли слегка наклоняют ось
    assert out["right"] < -0.97


def test_gun_barrel_left_grip_down():
    """Ствол длинный и тонкий, рукоять у задней части торчит вниз"""
    out = _run("""
      const pts = [];
      for (let x = 0; x <= 10; x += 0.1) for (let y = 0; y <= 1; y += 0.1) pts.push([x, y, 0]);
      for (let x = 1; x <= 3; x += 0.1) for (let y = -4; y < 0; y += 0.1) pts.push([x, y, 0]);
      for (const p of pts.slice()) pts.push([p[0], p[1], 0.4]);
      const pose = itemPose(place(pts, U, V, W));
      return { right: dot(pose.right, U), up: dot(pose.up, V),
               back: dot(pose.back, [U[1]*V[2]-U[2]*V[1], U[2]*V[0]-U[0]*V[2], U[0]*V[1]-U[1]*V[0]]) };
    """)
    assert out["right"] < -0.99        # дуло на x = 10 - влево
    assert out["up"] > 0.99            # рукоять внизу
    assert abs(abs(out["back"]) - 1) < 1e-6


def test_prior_decides_sides_the_shape_gets_wrong():
    """Ружьё с широким торцом ствола: по форме перёд - приклад. Подсказка
    кости руки знает, что ствол смотрит в +Y, а верх - в -Z"""
    out = _run("""
      const pts = [];
      // широкий ствол от y = 0 до 10, тонкий кончик приклада у y = -3
      for (let y = -3; y <= 10; y += 0.05) {
        const h = y < 0 ? 0.2 + 0.25 * (y + 3) : 1;
        for (let k = -1; k <= 1; k += 0.25) for (const x of [-0.3, 0.3]) pts.push([x, y, h * k]);
      }
      const pose = itemPose(pts.flat(), { forward: [0, 1, 0], up: [0, 0, -1] });
      const shape = itemPose(pts.flat());
      return { right: pose.right[1], up: pose.up[2], shapeRight: shape.right[1] };
    """)
    assert out["shapeRight"] > 0.99     # одна форма кладёт ствол вправо
    assert out["right"] < -0.99         # ствол (+Y) влево
    assert out["up"] < -0.99


def test_axes_are_orthonormal():
    out = _run("""
      const pts = [];
      for (let i = 0; i < 500; i++) pts.push([Math.sin(i) * 5, Math.cos(i * 1.3) * 2, Math.sin(i * 0.7)]);
      const p = itemPose(place(pts, U, V, W));
      return [dot(p.right, p.right), dot(p.up, p.up), dot(p.back, p.back),
              dot(p.right, p.up), dot(p.right, p.back), dot(p.up, p.back)];
    """)
    for value, want in zip(out, [1, 1, 1, 0, 0, 0]):
        assert abs(value - want) < 1e-9


def test_eigen_solves_a_symmetric_matrix():
    out = _run("""
      const m = [[4, 1, 2], [1, 3, 0.5], [2, 0.5, 5]];
      return eigenSym3(m).map(({ value, vector: v }) =>
        Math.max(...[0, 1, 2].map((r) => Math.abs(dot(m[r], v) - value * v[r]))));
    """)
    assert max(out) < 1e-9


def test_too_few_points_is_none():
    assert _run("return itemPose([1, 2, 3]);") is None


def test_compact_item_lies_along_model_axes():
    """Прерыватель: длина к высоте 1,1, иконка снята наискось. Ствол - ось,
    ближайшая к перёду иконки, наклон иконки в кадр не идёт"""
    out = _run("""
      const pts = [];
      for (let x = 0; x <= 11; x += 0.25) for (let y = 0; y <= 4; y += 0.25) pts.push([x, y, 0], [x, y, 3]);
      for (let x = 7; x <= 11; x += 0.25) for (let y = -6; y < 0; y += 0.25) pts.push([x, y, 0], [x, y, 3]);
      const c = Math.cos(0.45), s = Math.sin(0.45);
      // Камера Source: view = forward x up
      const pose = itemPose(pts.flat(), { forward: [c, -s, 0], up: [s, c, 0], view: [0, 0, 1] });
      return [pose.right, pose.up, pose.back];
    """)
    assert out == [[-1, 0, 0], [0, 1, 0], [0, 0, -1]]


def test_icon_camera_picks_the_side_of_a_wide_gun():
    """Scatterdrum: барабан торчит вбок, бок шире высоты. Иконка смотрит
    сбоку - туда и смотрим, а не сверху"""
    out = _run("""
      const pts = [];
      for (let y = 0; y <= 30; y += 0.5) for (const x of [-1, 1]) for (const z of [-2, 2]) pts.push([x, y, z]);
      for (let a = 0; a < 6.28; a += 0.2) pts.push([6 * Math.cos(a), 12, 4 * Math.sin(a)]);
      const pose = itemPose(pts.flat(), { forward: [-0.5, 0.86, 0], up: [-0.3, -0.2, -0.93],
                                          view: [-0.8, -0.48, 0.36] });
      return [pose.right, pose.up, pose.back];
    """)
    assert out[0] == [0, -1, 0]           # ствол (+Y) влево
    assert out[1] == [0, 0, -1]           # верх как у руки
    assert out[2] == [1, 0, 0]            # смотрим сбоку, с той стороны, что иконка


def test_thin_side_faces_viewer_when_icon_is_between_axes():
    """Лопата: камера иконки смотрит между двумя осями (одна на все лопаты
    Valve). Видна лопасть, а не ребро"""
    out = _run("""
      const pts = [];
      for (let z = 0; z <= 36; z += 0.5) for (const x of [-0.5, 0.5]) for (const y of [-0.5, 0.5]) pts.push([x, y, z]);
      for (let z = 26; z <= 36; z += 0.5) for (let x = -6; x <= 6; x += 0.5) pts.push([x, -1.5, z], [x, 1.5, z]);
      const pose = itemPose(pts.flat(), { forward: [-0.49, 0.22, -0.85], up: [0.56, -0.66, -0.5],
                                          view: [-0.67, -0.72, 0.2] });
      return pose.back;
    """)
    assert [abs(v) for v in out] == [0, 1, 0]   # смотрим вдоль тонкой оси Y


def test_model_askew_to_its_axes_falls_back_to_shape():
    """Мод, сделанный наискось к осям: привязка к осям положила бы его косо,
    ось берёт форма"""
    out = _run("""
      const pts = [];
      for (let x = 0; x <= 10; x += 0.1) for (let y = 0; y <= 1; y += 0.1) pts.push([x, y, 0], [x, y, 0.4]);
      const pose = itemPose(place(pts, U, V, W), { forward: U, up: V });
      return { right: dot(pose.right, U) };
    """)
    assert out["right"] < -0.99


def test_long_item_ignores_icon_tilt():
    """Ружьё на иконке наклонено, но в кадре его длина остаётся горизонтальной"""
    out = _run("""
      const pts = [];
      for (let x = 0; x <= 10; x += 0.1) for (let y = 0; y <= 1; y += 0.1) pts.push([x, y, 0]);
      for (let x = 1; x <= 3; x += 0.1) for (let y = -4; y < 0; y += 0.1) pts.push([x, y, 0]);
      for (const p of pts.slice()) pts.push([p[0], p[1], 0.4]);
      // Камера иконки повёрнута на 20 градусов в плоскости модели
      const c = Math.cos(0.35), s = Math.sin(0.35);
      const pose = itemPose(pts.flat(), { forward: [c, s, 0], up: [-s, c, 0], view: [0, 0, -1] });
      return { right: pose.right[0], up: pose.up[1] };
    """)
    assert out["right"] < -0.99         # ствол строго влево, без наклона иконки
    assert out["up"] > 0.99


def test_flat_item_askew_to_axes_shows_its_face():
    """Chargin' Targe: в позе из анимации щит повёрнут к осям модели на 45°.
    Привязка к осям показала бы его косо - кадр смотрит на лицо щита"""
    out = _run("""
      const pts = [];
      const n = [Math.SQRT1_2, -Math.SQRT1_2, 0];          // нормаль щита наискось
      const a = [Math.SQRT1_2, Math.SQRT1_2, 0], b = [0, 0, 1];
      for (let r = 0; r <= 9; r += 0.5) for (let t = 0; t < 6.28; t += 0.2)
        for (const h of [-0.4, 0.4]) pts.push([0, 1, 2].map((k) =>
          r * Math.cos(t) * a[k] + r * Math.sin(t) * b[k] + h * n[k]));
      const pose = itemPose(pts.flat(), { forward: [0, 1, 0], up: [0, 0, -1], view: [-1, 0, 0] });
      return Math.abs(dot(pose.back, n));
    """)
    assert out > 0.99
