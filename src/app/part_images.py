"""
Картинки части: стопка слоёв снизу вверх, посадка каждой и замена стопки целиком

Соавтор PartsEditor: функции получают редактор первым аргументом (self), класс
назначает их себе. Мазки цветом и всё остальное про части - в parts_editor.py
"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING, Any, Dict, List, Optional

from src.domain.preview import part_specs

if TYPE_CHECKING:
    from src.app.parts_editor import PartsEditor


def set_part_texture(self: "PartsEditor", material: str = '', part: int = 0,
                     path: Optional[str] = None,
                     options: Optional[Dict[str, Any]] = None,
                     layer: Optional[int] = None) -> Dict[str, Any]:
    """
    Картинки одной части - слоями, снизу вверх

    ``path`` - новая картинка: без ``layer`` ложится ПОВЕРХ уже лежащих,
    с ним - заменяет названный слой. Без пути, но с ``options`` - правка
    посадки уже положенной (``layer``, по умолчанию верхней). Без того и
    другого - убрать названный слой либо все картинки части разом
    """
    found = self._parts_model(material)
    if isinstance(found, dict):
        return found
    model, obj_mat, card = found

    refused = self._refuse(model, obj_mat, int(part), [path] if path else [])
    if refused:
        return refused

    with self._lock:
        chosen = self.preview.part_textures.setdefault(self._slot(card), {})
        stack = list(chosen.get(int(part), []))
        at = None if layer is None else int(layer)
        if at is not None and not -len(stack) <= at < len(stack):
            return {'error': 'Такой картинки на части нет'}
        if path:
            entry = part_specs.image_spec(
                {**self._absolute_size(options, path, model, obj_mat, card,
                                       int(part)), 'path': path})
            if at is None:
                stack.append(entry)
            else:
                stack[at] = entry
        elif options is not None:
            if not stack:
                return {'error': 'На этой части нет картинки'}
            idx = -1 if at is None else at
            spec = dict(stack[idx])
            # Якорь переживает правку посадки: он говорит, В ЧЁМ картинка
            # живёт, а окно двигает её ВНУТРИ этого габарита
            fresh = part_specs.image_spec({**options, 'path': spec['path']})
            spec.update({k: v for k, v in fresh.items() if k not in ('path', 'anchor')})
            stack[idx] = spec
        elif at is None:
            stack = []
        else:
            del stack[at]
        jobs = self._put_stack(chosen, int(part), stack, model, obj_mat, card)
    return self._commit(jobs)

def set_part_layers(self: "PartsEditor", material: str = '', part: int = 0,
                    layers: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
    """Вся стопка картинок части разом, снизу вверх: так её сдаёт окно
    посадки - одна склейка и один шаг отмены на всё, что в нём сделано"""
    found = self._parts_model(material)
    if isinstance(found, dict):
        return found
    model, obj_mat, card = found
    # Битая запись - отказ, а не молча пропавший слой: ушло бы «снять всё»
    if not isinstance(layers or [], list) or not all(isinstance(x, dict) for x in layers or []):
        return {'error': 'Неверный список картинок'}
    stack = [part_specs.image_spec(x) for x in layers or []]
    refused = self._refuse(model, obj_mat, int(part), [s['path'] for s in stack])
    if refused:
        return refused
    with self._lock:
        chosen = self.preview.part_textures.setdefault(self._slot(card), {})
        jobs = self._put_stack(chosen, int(part), stack, model, obj_mat, card)
    return self._commit(jobs)

def refuse(self: "PartsEditor", model: Any, obj_mat: str, part: int,
            paths: List[str]) -> Optional[Dict[str, str]]:
    """Почему картинки на часть не положить. None - можно"""
    if any(not p or not os.path.isfile(p) for p in paths):
        return {'error': 'Файл не найден'}
    given = self._given(model, obj_mat, part) if paths else ''
    return {'error': f'Часть отдана материалу «{given}»: её красит его текстура'}             if given else None

def put_stack(self: "PartsEditor", chosen: Dict[int, Any], part: int, stack: List[Any],
               model: Any, obj_mat: str, card: str) -> List[Any]:
    """Под замком: стопка части на место (пустая - долой) и задания склейки"""
    if stack:
        chosen[part] = stack
    else:
        chosen.pop(part, None)
    return self._plans(model, obj_mat, card)

def absolute_size(self: "PartsEditor", options: Optional[Dict[str, Any]], path: str,
                   model: Any, obj_mat: str, card: str, part: int) -> Dict[str, Any]:
    """
    Посадка с размером В ДОЛЯХ ТЕКСТУРЫ (`size_uv`) - в масштабы части

    Так приходит вставка скопированной картинки: «того же размера» значит
    того же на текстуре, а масштаб считается от габарита части - один и
    тот же масштаб на другой детали дал бы другую картинку. Пересчёт здесь,
    а не на странице: габарит части, размер текстуры и картинки знает
    Python, и склейка вписывает ровно по этим числам (`place_image`)
    """
    opts = dict(options or {})
    size = opts.pop('size_uv', None)
    one = next((p for p in model.parts_of(obj_mat) if p.index == part), None)
    shape = self._texture_shape(card)
    if not size or one is None or not shape:
        return opts
    try:
        from PIL import Image
        with Image.open(path) as im:
            iw, ih = max(1, im.width), max(1, im.height)
    except (OSError, ValueError):
        return opts
    tex_w, tex_h = shape
    u0, v0, u1, v1 = one.uv_bbox
    bw = max(1e-6, (u1 - u0) * tex_w)
    bh = max(1e-6, (v1 - v0) * tex_h)
    fit = str(opts.get('fit') or 'contain')
    if fit == 'stretch':
        base_w, base_h = bw, bh
    else:
        k = (max if fit == 'cover' else min)(bw / iw, bh / ih)
        base_w, base_h = iw * k, ih * k
    opts['scale'] = float(size[0]) * tex_w / base_w
    opts['scale_y'] = float(size[1]) * tex_h / base_h
    opts['offset'] = [0.0, 0.0]            # на новой детали - по её центру
    return opts

def move_part_texture(self: "PartsEditor", material: str = '', part: int = 0,
                      layer: int = 0, to: int = 0) -> Dict[str, Any]:
    """Переставляет картинку части в стопке: порядок и есть наложение"""
    found = self._parts_model(material)
    if isinstance(found, dict):
        return found
    model, obj_mat, card = found

    with self._lock:
        chosen = self.preview.part_textures.setdefault(self._slot(card), {})
        stack = list(chosen.get(int(part), []))
        n = len(stack)
        src, dst = int(layer), int(to)
        if not (-n <= src < n and -n <= dst < n):
            return {'error': 'Такой картинки на части нет'}
        src %= n
        dst %= n
        if src == dst:
            return self._host.view_state()
        stack.insert(dst, stack.pop(src))
        jobs = self._put_stack(chosen, int(part), stack, model, obj_mat, card)
    return self._commit(jobs)
