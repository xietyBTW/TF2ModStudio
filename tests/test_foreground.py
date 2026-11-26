"""Фон уступает странице, но только фон и не дольше потолка"""

from __future__ import annotations

import threading
import time

from src.shared import foreground


def _yield_in_background(needed=lambda: False, times=1) -> float:
    took = []

    def run():
        foreground.mark_background()
        t = time.monotonic()
        for _ in range(times):
            foreground.yield_to_page(needed)
        took.append(time.monotonic() - t)

    th = threading.Thread(target=run)
    th.start()
    th.join(10)
    return took[0]


def test_background_waits_for_page_request_then_quiet():
    release = threading.Event()

    def page():
        with foreground.page_request():
            release.wait(5)

    th = threading.Thread(target=page)
    th.start()
    time.sleep(0.05)
    threading.Timer(0.2, release.set).start()
    took = _yield_in_background()
    th.join()
    # Запрос шёл ещё ~0,15 с, потом тишина QUIET_S
    assert 0.15 + foreground.QUIET_S - 0.05 <= took < foreground.MAX_WAIT_S


def test_page_thread_never_waits():
    with foreground.page_request():
        t = time.monotonic()
        foreground.yield_to_page()
        assert time.monotonic() - t < 0.05


def test_background_wait_is_capped(monkeypatch):
    monkeypatch.setattr(foreground, 'MAX_WAIT_S', 0.3)
    release = threading.Event()

    def page():
        with foreground.page_request():
            release.wait(5)

    th = threading.Thread(target=page)
    th.start()
    time.sleep(0.05)
    try:
        assert _yield_in_background() < 1.0
    finally:
        release.set()
        th.join()


def test_needed_wakes_background_at_once():
    release = threading.Event()
    wanted = threading.Event()

    def page():
        with foreground.page_request():
            release.wait(5)

    th = threading.Thread(target=page)
    th.start()
    time.sleep(0.05)

    def want():
        wanted.set()
        foreground.wake()

    threading.Timer(0.1, want).start()
    try:
        assert _yield_in_background(wanted.is_set) < 0.5
    finally:
        release.set()
        th.join()


def test_total_budget_bounds_many_yields(monkeypatch):
    monkeypatch.setattr(foreground, 'MAX_WAIT_S', 0.2)
    monkeypatch.setattr(foreground, 'TOTAL_WAIT_S', 0.5)
    release = threading.Event()

    def page():
        with foreground.page_request():
            release.wait(10)

    th = threading.Thread(target=page)
    th.start()
    time.sleep(0.05)
    try:
        # Двадцать уступок по 0,2 с - это 4 с, а бюджет 0,5
        assert _yield_in_background(times=20) < 1.0
    finally:
        release.set()
        th.join()
