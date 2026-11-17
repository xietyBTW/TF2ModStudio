"""
Гифка на материале: кадры для 3D

Браузер кладёт на модель только первый кадр гифки, поэтому анимированная
текстура из альбома на модели стояла неподвижно, хотя в мод уходила
анимацией. Вьювер умеет крутить список PNG (`loadAnimatedTexture`): кадры
раскладывает Python, тем же PIL, что и сборка

Разбор идёт фоном: шестьдесят кадров - это секунды, а состояние показа
спрашивают после каждого действия. Готовые кадры отдаёт `for_scene`, о
готовности страница узнаёт событием `texture_animated` и спрашивает
состояние заново
"""

from __future__ import annotations

import hashlib
import os
import threading
from typing import Any, Dict, Optional, Tuple

from src.shared.logging_config import get_logger

logger = get_logger(__name__)

#: Что может быть анимацией. Остальное не открываем вовсе
_ANIMATED_EXTS = ('.gif', '.png', '.apng', '.webp')


def model_gifs_on() -> bool:
    """Настройка «Крутить гифки на модели»: одна на карточки и на части"""
    from src.config.app_config import AppConfig
    return bool(AppConfig.load_config().get('parts_animation'))


class TextureAnimations:
    """Кадры анимированных текстур сцены. Живёт в сеансе (`session().animations`)"""

    #: Длинная сторона кадра: вьювер держит все кадры текстурами на
    #: видеокарте, 60 кадров 1024² - это 240 МБ
    PREVIEW_SIZE = 1024
    #: Сколько гифок крутить на модели сразу: каждая - свой набор кадров на
    #: видеокарте. Остальные материалы стоят первым кадром
    MAX_LIVE = 4
    #: Сколько разобранных анимаций помнить
    _KEEP = 6

    def __init__(self, host) -> None:
        self._host = host
        self._lock = threading.Lock()
        #: {отпечаток файла: (кадры, кадров в секунду)}
        self._ready: Dict[Tuple[str, int, int], Tuple[list, int]] = {}
        self._pending: set = set()
        #: Отпечатки обычных картинок: второй раз их не открываем
        self._still: set = set()

    def for_scene(self, scene: Dict[str, str]) -> Dict[str, Dict[str, Any]]:
        """
        {меш: {still, frames, fps}} для анимированных текстур сцены

        Чего ещё нет - начинает разбираться фоном и приедет после события
        `texture_animated`. При выключенной настройке пусто: страница кладёт
        на меш неподвижную картинку, и вьювер анимацию гасит
        """
        from src.services import texture_compose_service as compose

        if not model_gifs_on():
            return {}

        out: Dict[str, Dict[str, Any]] = {}
        moving = 0
        for mesh, path in (scene or {}).items():
            key = _stamp(path)
            if key is None or key in self._still:
                continue
            with self._lock:
                got = self._ready.get(key)
                waiting = key in self._pending
            # Число кадров - это чтение заголовка, его потоком не выносим
            if not (got or waiting) and compose.frame_count(path) < 2:
                if len(self._still) > 512:
                    self._still.clear()
                self._still.add(key)
                continue
            moving += 1
            if moving > self.MAX_LIVE:
                break
            if got:
                out[mesh] = {'still': path, 'frames': list(got[0]), 'fps': got[1]}
            elif not waiting:
                with self._lock:
                    self._pending.add(key)
                threading.Thread(target=self._export, args=(key,), daemon=True,
                                 name='texture-anim').start()
        return out

    def _export(self, key: Tuple[str, int, int]) -> None:
        from src.services import texture_compose_service as compose

        path = key[0]
        frames: list = []
        fps = 0
        try:
            digest = hashlib.blake2b(repr(key).encode('utf-8'), digest_size=8).hexdigest()
            out_dir = os.path.join(self._host._work_dir(), 'texanim', digest)
            frames, delays = compose.export_frames(
                path, out_dir, 'frame', size=self.PREVIEW_SIZE)
            fps = compose.fps_of(delays)
        except Exception as exc:                  # noqa: BLE001 - превью обойдётся кадром
            logger.warning(f"[anim] кадры {os.path.basename(path)} не разобраны: {exc}")
            frames = []
        with self._lock:
            self._pending.discard(key)
            if frames:
                self._ready[key] = (frames, fps)
                while len(self._ready) > self._KEEP:
                    self._ready.pop(next(iter(self._ready)))
        if frames:
            self._host._put('texture_animated', still=path)
        else:
            self._still.add(key)


def _stamp(path: Optional[str]) -> Optional[Tuple[str, int, int]]:
    """Отпечаток файла, который может быть анимацией; None - точно не она"""
    if not path or not path.lower().endswith(_ANIMATED_EXTS):
        return None
    try:
        st = os.stat(path)
    except OSError:
        return None
    return path, st.st_mtime_ns, st.st_size
