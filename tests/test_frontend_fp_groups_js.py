"""
Анимации от первого лица группами: что в какую кнопку и когда шаг цепочки
закончен (frontend/mockup/fp-groups.js)

Тест пропускается, если node недоступен
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

GROUPS_JS = Path("frontend/mockup/fp-groups.js").resolve()

pytestmark = pytest.mark.skipif(
    shutil.which("node") is None or not GROUPS_JS.exists(),
    reason="node недоступен или fp-groups.js не найден")


def _run(body: str):
    script = f"import * as g from {GROUPS_JS.as_uri()!r};\nconsole.log(JSON.stringify({body}));"
    out = subprocess.run(["node", "--input-type=module", "-e", script],
                         capture_output=True, text=True, encoding="utf-8",
                         timeout=30, check=True)
    return json.loads(out.stdout)


def test_full_weapon_folds_into_five_groups_and_keeps_the_rest():
    actions = ["IDLE", "DRAW", "HOLSTER", "FIRE", "ALT_FIRE", "CRIT", "RELOAD",
               "RELOAD_START", "RELOAD_FINISH", "INSPECT_START", "INSPECT_IDLE", "INSPECT_END"]
    res = _run(f"g.fpGroups({json.dumps(actions)})")
    assert [x["label"] for x in res["groups"]] == ["Покой", "Достать", "Выстрел", "Перезарядка", "Осмотр"]
    assert res["groups"][3]["chain"] == ["RELOAD_START", "RELOAD", "RELOAD_FINISH"]
    assert res["rest"] == ["HOLSTER", "ALT_FIRE", "CRIT"]


def test_missing_actions_shorten_chains_and_drop_empty_groups():
    res = _run('g.fpGroups(["IDLE", "RELOAD", "INSPECT_IDLE"])')
    assert res["groups"] == [{"label": "Покой", "chain": ["IDLE"]},
                             {"label": "Перезарядка", "chain": ["RELOAD"]},
                             {"label": "Осмотр", "chain": ["INSPECT_IDLE"]}]


def test_step_ends_at_the_end_or_after_a_full_loop():
    # Редкие кадры: доля прыгнула с 0.77 на 0.54 - клип доиграл круг, и это
    # видно только по счёту кругов вьювера
    assert _run("[g.stepDone(0.98, 0), g.stepDone(0.54, 1), g.stepDone(0.5, 0),"
                " g.stepDone(null, null), g.stepDone(0.2, undefined)]") == [
        True, True, False, False, False]
    assert _run("[g.chainProgress(1, 3, 0.5), g.chainProgress(0, 0, 0.5)]") == [0.5, 0]
