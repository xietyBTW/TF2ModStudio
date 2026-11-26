"""Ответы сборке на «чем красить» - по предмету, который собирается

Тело класса собирается полминуты. Открытый за это время другой предмет
отдавал сборке свои картинки: синие голова и медали солдата получали
текстуру маски шпиона
"""

import threading
from types import SimpleNamespace

from src.app.build_editor import BuildEditor


class _State:
    def __init__(self, answer):
        self.answer = answer

    def build_answer(self, material):
        return self.answer


def test_answer_comes_from_the_item_being_built():
    got = []
    host = SimpleNamespace(
        _lock=threading.Lock(),
        preview=SimpleNamespace(textures=_State('other_item.png'), custom_vpk_mode=False),
        parts=SimpleNamespace(baked_path=lambda p: p),
        _put=lambda *a, **k: got.append(('put', a, k)))
    editor = BuildEditor(host)
    editor._build = SimpleNamespace(set_extra_texture_result=got.append,
                                    isInterruptionRequested=lambda: False)
    editor._answers = _State('built_item.png')

    editor._on_build_needs_texture('soldier_head_blue', 'soldier_body')

    assert got == ['built_item.png']
