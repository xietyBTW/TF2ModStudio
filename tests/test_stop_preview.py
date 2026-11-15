"""
Уход от предмета (смена раздела) гасит всё, что собиралось для него

Оставшийся воркер сцены досчитывал вид от первого лица и присылал его уже в
чужой раздел: оружие висело в кадре над каталогом шапок
"""

from unittest.mock import Mock

from src.app.session import AppSession


def test_stop_preview_stops_model_and_scene_workers():
    session = AppSession.__new__(AppSession)
    workers = ("controller", "viewmodel", "taunt", "death")
    for name in (*workers, "decor"):
        setattr(session, name, Mock())

    assert session.stop_preview() == {"stopped": True}

    for name in workers:
        getattr(session, name).stop.assert_called_once_with()
    session.decor.forget.assert_called_once_with()
