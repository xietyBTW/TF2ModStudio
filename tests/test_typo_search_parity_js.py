"""Поиск с опечатками - одно правило в Python и в JS

Каталог ищет в Python (src/shared/text_search.py), выпадающие списки - в
странице (frontend/mockup/typo-search.js). Копии сверяются здесь на одних
входах: разойдись они, одно и то же слово находилось бы в каталоге и
пропадало в списке. Тест пропускается, если node недоступен
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from src.shared.text_search import prefix_typos, typo_budget, words_of

JS = Path("frontend/mockup/typo-search.js").resolve()

pytestmark = pytest.mark.skipif(shutil.which("node") is None or not JS.exists(),
                                reason="node недоступен или typo-search.js не найден")

_WORDS = ["fedora", "fedoras", "fire", "affirm", "burning", "superrare", "ёлка",
          "scattergun", "scatergun", "rocket", "a", "ab", "abc", "abcd", "шапка"]
_QUERIES = ["fedra", "fedroa", "fire", "fier", "burnign", "suprerare", "елка",
            "scatergun", "rokcet", "ab", "abcde", "шпака", "x"]
_TEXTS = ["superrare_burning1", "Ёлка-2024 (новая)", "c_scattergun.mdl", ""]


def _js():
    script = f"""
import {{ typoBudget, prefixTypos, wordsOf }} from {JS.as_uri()!r};
const words = {json.dumps(_WORDS)}, queries = {json.dumps(_QUERIES)};
const texts = {json.dumps(_TEXTS)};
const typos = queries.map((q) => words.map((w) => prefixTypos(q, w, typoBudget(q))));
console.log(JSON.stringify({{
  budgets: queries.map(typoBudget), typos, words: texts.map(wordsOf) }}));
"""
    out = subprocess.run(["node", "--input-type=module", "-e", script],
                         capture_output=True, text=True, encoding="utf-8", check=True)
    return json.loads(out.stdout)


def test_python_and_js_agree():
    js = _js()
    assert js["budgets"] == [typo_budget(q) for q in _QUERIES]
    assert js["typos"] == [[prefix_typos(q, w, typo_budget(q)) for w in _WORDS]
                           for q in _QUERIES]
    assert js["words"] == [words_of(t) for t in _TEXTS]
