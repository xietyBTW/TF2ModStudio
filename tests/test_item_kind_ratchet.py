"""Вид предмета спрашивают у ItemKind, а не у строки режима

Прямая проверка (`mode == 'hat'`, `mode in HAND_MODE_KEYS`) знает вид по
имени и молчит, когда появляется новый вид или меняется поведение старого.
Ответы на «как обращаться с предметом» живут в таблице src/data/item_kinds"""

import re
from pathlib import Path

_SRC = Path(__file__).resolve().parent.parent / "src"
#: Где режим и виды определяются - там проверки по имени законны
_HOME = {"data/item_kinds.py", "data/player_hands.py", "data/player_characters.py"}
_RAW = re.compile(
    r"""mode\W*\)?\s*[!=]=\s*['"](hat|custom)['"]"""
    r"""|['"](hat|custom)['"]\s*[!=]=\s*[\w.]*mode"""
    r"""|mode\s+(not\s+)?in\s+\(\s*['"](hat|custom)['"]"""
    r"""|\bin\s+(HAND_MODE_KEYS|PLAYER_BODY_MODE_KEYS)\b"""
    r"""|[!=]=\s*SPY_MASK_MODE_KEY\b""")


def _offenders():
    for path in sorted(_SRC.rglob("*.py")):
        rel = path.relative_to(_SRC).as_posix()
        if rel in _HOME:
            continue
        for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            code = line.split("#", 1)[0]
            if _RAW.search(code):
                yield f"src/{rel}:{n}: {line.strip()}"


def test_kind_is_asked_not_spelled():
    found = list(_offenders())
    assert not found, "вид предмета - через kind_of(mode):\n" + "\n".join(found)


def test_the_rule_catches_a_raw_check():
    assert _RAW.search("if mode == 'hat':")
    assert _RAW.search("x = mode in HAND_MODE_KEYS")
    assert _RAW.search("if getattr(self, '_mode', '') != 'hat':")
    assert _RAW.search("if 'hat' == mode:")
    assert _RAW.search("if mode in ('hat', 'custom'):")
    assert not _RAW.search("if kind_of(mode).is_hat:")
    assert not _RAW.search("if category != 'custom':")
