"""
Страница первая, прогрев потом

Прогрев индексов игры (warm_up.py) идёт фоном сразу после старта, а на новом
ПК он долгий: таблица текстур игры с холодного HDD читается полторы минуты.
Всё это время он делил с запросами страницы диск и GIL, и иконки каталога
оружия на первом запуске приходили за 5 с вместо 1,7

Мост отмечает каждый запрос страницы (`page_request`), фоновые потоки в
удобных местах зовут `yield_to_page` и ждут, пока страница затихнет. Ждут
только потоки, отмеченные `mark_background`: рабочий поток, которого страница
ждёт прямо сейчас, уступать ей не должен
"""

from __future__ import annotations

import threading
import time
from contextlib import contextmanager
from typing import Callable, Iterator

#: Тишина после последнего запроса, прежде чем фон продолжит. Каталог просит
#: иконки пачками одну за другой, и между пачками фон влезать не должен
QUIET_S = 0.3

#: Дольше одного раза фон не ждёт: страница может дёргать сервер без конца
#: (журнал раз в секунду), а может и ждать того, что фон держит под замком
MAX_WAIT_S = 3.0

#: Сколько всего фоновый поток уступает за жизнь. Долгий запрос страницы
#: иначе стоил бы фону по MAX_WAIT_S на каждой из сотен уступок
TOTAL_WAIT_S = 15.0

_cv = threading.Condition()
_active = 0
_last = 0.0
_local = threading.local()


@contextmanager
def page_request() -> Iterator[None]:
    """Отмечает запрос страницы на время его обработки"""
    global _active, _last
    with _cv:
        _active += 1
    try:
        yield
    finally:
        with _cv:
            _active -= 1
            _last = time.monotonic()
            _cv.notify_all()


def mark_background() -> None:
    """Текущий поток - фоновый, ему можно ждать страницу"""
    _local.budget = TOTAL_WAIT_S


def wake() -> None:
    """Будит ждущий фон, чтобы он заново спросил `needed`"""
    with _cv:
        _cv.notify_all()


def yield_to_page(needed: Callable[[], bool] = lambda: False) -> None:
    """Ждёт, пока страница затихнет, но не дольше MAX_WAIT_S за раз и
    TOTAL_WAIT_S за жизнь потока. `needed()` - фон нужен кому-то прямо сейчас,
    ждать нельзя (после смены зовут `wake`). В нефоновом потоке ничего не
    делает"""
    budget = getattr(_local, 'budget', 0.0)
    if budget <= 0:
        return
    start = time.monotonic()
    deadline = start + min(MAX_WAIT_S, budget)
    try:
        with _cv:
            while True:
                now = time.monotonic()
                calm = now - _last
                if ((not _active and calm >= QUIET_S) or now >= deadline
                        or needed()):
                    return
                _cv.wait(min(deadline - now, max(QUIET_S - calm, 0.02)))
    finally:
        _local.budget = budget - (time.monotonic() - start)
