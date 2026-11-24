"""Классы TF2: список, как класс пишется в путях моделей, класс модели по пути

Одно правило на всё приложение. Главная ловушка - подрывник: класс зовётся
`demoman`, а файлы моделей у него `..._demo.mdl` (в игре 910 таких моделей и
ни одной `_demoman`). Копии, знавшие только `demoman`, молча теряли его
модель: многоклассовая шапка собиралась без подрывника"""

import re
from typing import Optional, Tuple

#: Классы в порядке игры
CLASSES: Tuple[str, ...] = ('scout', 'soldier', 'pyro', 'demoman', 'heavy',
                            'engineer', 'medic', 'sniper', 'spy')

_MODEL_TOKEN = {'demoman': 'demo'}

#: Токены классов в путях игровых моделей
MODEL_TOKENS: Tuple[str, ...] = tuple(_MODEL_TOKEN.get(c, c) for c in CLASSES)

#: Порядок перебора `%s` у шапок: модель и текстура пробуются одним
#: порядком, иначе превью сводило бы модель одного класса с текстурой другого
PROBE_TOKENS: Tuple[str, ...] = ('heavy',) + tuple(t for t in MODEL_TOKENS if t != 'heavy')

_CLASS_OF_TOKEN = {_MODEL_TOKEN.get(c, c): c for c in CLASSES}
#: `_demoman` встречается в старых модах - класс по нему тоже узнаём
_CLASS_OF_TOKEN['demoman'] = 'demoman'
_SUFFIX = re.compile(r'_(' + '|'.join(sorted(_CLASS_OF_TOKEN, key=len, reverse=True))
                     + r')(\.mdl)?$', re.IGNORECASE)


def model_token(cls: str) -> str:
    """Как класс пишется в пути модели: `demoman` -> `demo`"""
    low = (cls or '').lower()
    return _MODEL_TOKEN.get(low, low)


def class_of_model(path: str) -> Optional[str]:
    """Класс модели по суффиксу имени (`hat_demo.mdl` -> demoman) или None"""
    m = _SUFFIX.search(str(path or '').replace('\\', '/'))
    return _CLASS_OF_TOKEN[m.group(1).lower()] if m else None


def with_class(path: str, cls: str) -> str:
    """Тот же путь с суффиксом другого класса (`hat_heavy.mdl` -> `hat_demo.mdl`)"""
    return _SUFFIX.sub(lambda m: f'_{model_token(cls)}{m.group(2) or ""}', str(path), count=1)


def strip_class(stem: str) -> str:
    """Имя без суффикса класса: `hat_demo` -> `hat`"""
    return _SUFFIX.sub('', str(stem or ''), count=1)
