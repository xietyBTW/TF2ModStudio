"""
Гифка на материале: кадры для 3D (src/app/texture_animation.py)

Браузер кладёт на модель только первый кадр гифки. Кадры раскладывает Python
фоном и отдаёт их в состоянии показа, когда они готовы
"""

import threading
import time

import pytest
from PIL import Image

from src.app import texture_animation
from src.app.texture_animation import TextureAnimations
from src.services import texture_compose_service as compose


@pytest.fixture(autouse=True)
def _gifs_on(monkeypatch):
    # Настройка читается из конфига машины - тесты на него не смотрят
    monkeypatch.setattr(texture_animation, 'model_gifs_on', lambda: True)


class _Host:
    def __init__(self, folder):
        self._folder = str(folder)
        self.events = []
        self.sent = threading.Event()

    def _work_dir(self):
        return self._folder

    def _put(self, kind, **payload):
        self.events.append((kind, payload))
        self.sent.set()


def _gif(path, frames=4, size=(8, 8), duration=50):
    images = [Image.new('RGB', size, (i * 60, 0, 0)) for i in range(frames)]
    images[0].save(path, save_all=True, append_images=images[1:],
                   duration=duration, loop=0)
    return str(path)


def _png(path):
    Image.new('RGBA', (8, 8), (1, 2, 3, 255)).save(path)
    return str(path)


def test_gif_frames_arrive_after_the_background_export(tmp_path):
    host = _Host(tmp_path / 'work')
    anims = TextureAnimations(host)
    gif = _gif(tmp_path / 'fire.gif')
    scene = {'c_gun': gif, 'hands': _png(tmp_path / 'hands.png')}

    assert anims.for_scene(scene) == {}, "кадров ещё нет - разбор идёт фоном"
    assert host.sent.wait(10)
    assert host.events == [('texture_animated', {'still': gif})]

    got = anims.for_scene(scene)
    assert list(got) == ['c_gun']
    assert got['c_gun']['still'] == gif
    assert len(got['c_gun']['frames']) == 4
    assert got['c_gun']['fps'] == 20
    with Image.open(got['c_gun']['frames'][2]) as frame:
        assert frame.convert('RGB').getpixel((0, 0))[0] > 100


def test_setting_off_gives_no_frames_and_starts_nothing(tmp_path, monkeypatch):
    host = _Host(tmp_path / 'work')
    anims = TextureAnimations(host)
    gif = _gif(tmp_path / 'fire.gif')

    monkeypatch.setattr(texture_animation, 'model_gifs_on', lambda: False)
    assert anims.for_scene({'m': gif}) == {}
    assert not host.sent.wait(0.2), "при выключенной настройке кадры не считаем"

    monkeypatch.setattr(texture_animation, 'model_gifs_on', lambda: True)
    anims.for_scene({'m': gif})
    assert host.sent.wait(10)
    assert list(anims.for_scene({'m': gif})) == ['m']

    monkeypatch.setattr(texture_animation, 'model_gifs_on', lambda: False)
    assert anims.for_scene({'m': gif}) == {}, "готовые кадры тоже не отдаём"


def test_every_gif_of_the_scene_plays_up_to_the_cap(tmp_path, monkeypatch):
    host = _Host(tmp_path / 'work')
    anims = TextureAnimations(host)
    monkeypatch.setattr(TextureAnimations, 'MAX_LIVE', 2)
    scene = {f'm{i}': _gif(tmp_path / f'{i}.gif', frames=2) for i in range(3)}
    scene['still'] = _png(tmp_path / 'still.png')

    anims.for_scene(scene)
    deadline = time.time() + 10
    while len(anims.for_scene(scene)) < 2 and time.time() < deadline:
        time.sleep(0.02)
    assert list(anims.for_scene(scene)) == ['m0', 'm1'], "третья гифка стоит кадром"
    assert len(host.events) == 2


def test_export_starts_once_while_it_is_running(tmp_path, monkeypatch):
    host = _Host(tmp_path / 'work')
    anims = TextureAnimations(host)
    gif = _gif(tmp_path / 'a.gif')
    gate = threading.Event()
    calls = []
    real = compose.export_frames

    def slow(*args, **kwargs):
        calls.append(1)
        gate.wait(10)
        return real(*args, **kwargs)

    monkeypatch.setattr(compose, 'export_frames', slow)
    for _ in range(3):
        assert anims.for_scene({'m': gif}) == {}
    gate.set()
    assert host.sent.wait(10)
    assert calls == [1]


def test_still_pictures_are_left_alone(tmp_path, monkeypatch):
    host = _Host(tmp_path / 'work')
    anims = TextureAnimations(host)
    scene = {'a': _png(tmp_path / 'a.png'), 'b': str(tmp_path / 'b.vtf'),
             'c': str(tmp_path / 'missing.gif'), 'd': ''}
    assert anims.for_scene(scene) == {}
    counted = []
    monkeypatch.setattr(compose, 'frame_count', lambda p: counted.append(p) or 1)
    assert anims.for_scene(scene) == {}
    assert counted == [], "обычную картинку второй раз не открываем"
    time.sleep(0.05)
    assert host.events == []


def test_changed_file_is_exported_again(tmp_path):
    import os

    host = _Host(tmp_path / 'work')
    anims = TextureAnimations(host)
    gif = _gif(tmp_path / 'a.gif', frames=2)
    anims.for_scene({'m': gif})
    assert host.sent.wait(10)
    assert len(anims.for_scene({'m': gif})['m']['frames']) == 2

    host.sent.clear()
    _gif(tmp_path / 'a.gif', frames=5)
    os.utime(gif, ns=(7_000_000_000, 7_000_000_000))
    assert anims.for_scene({'m': gif}) == {}
    assert host.sent.wait(10)
    assert len(anims.for_scene({'m': gif})['m']['frames']) == 5


def test_frames_are_shrunk_for_the_viewer(tmp_path):
    gif = _gif(tmp_path / 'big.gif', frames=2, size=(64, 32))
    frames, delays = compose.export_frames(gif, str(tmp_path / 'out'), 'f', size=16)
    assert len(frames) == 2 and delays == [50, 50]
    with Image.open(frames[0]) as frame:
        assert frame.size == (16, 8)
    full, _ = compose.export_frames(gif, str(tmp_path / 'full'), 'f')
    with Image.open(full[0]) as frame:
        assert frame.size == (64, 32)


@pytest.mark.parametrize('delays, fps', [([100, 100], 10), ([50, 50, 50], 20),
                                         ([10, 10], 10), ([], 10), ([5000], 1)])
def test_fps_of(delays, fps):
    assert compose.fps_of(delays) == fps
