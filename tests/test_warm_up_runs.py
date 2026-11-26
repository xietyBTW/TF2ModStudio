"""Прогрев идёт одним потоком: запрос во время круга - следующий круг"""

from __future__ import annotations

import threading
import time

from src.app import warm_up


def test_second_request_runs_after_first(monkeypatch):
    calls = []
    gate = threading.Event()

    def fake_warm(host, root):
        calls.append(root)
        if len(calls) == 1:
            gate.wait(5)

    monkeypatch.setattr(warm_up, '_warm', fake_warm)
    monkeypatch.setattr(warm_up, '_resolve', lambda root: root)

    warm_up.start(None, 'A')
    time.sleep(0.05)
    warm_up.start(None, 'B')
    warm_up.start(None, 'C')          # пока идёт первый круг, побеждает последний
    gate.set()
    for _ in range(100):
        if warm_up._thread is None:
            break
        time.sleep(0.02)
    assert calls == ['A', 'C']
    assert warm_up._thread is None


def test_changed_root_stops_old_run(monkeypatch):
    monkeypatch.setattr(warm_up, '_next', 'other')
    assert warm_up._changed('mine')
    assert not warm_up._changed('other')
    monkeypatch.setattr(warm_up, '_next', None)
    assert not warm_up._changed('mine')
