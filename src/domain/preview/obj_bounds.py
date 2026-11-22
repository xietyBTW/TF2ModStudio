"""
Габариты модели для вписывания в кадр

Считается в Python намеренно: bounding box у Three.js сразу после загрузки
ненадёжен, а от центра и масштаба зависит, попадёт модель в кадр или уедет
за него. Правило не зависит ни от Qt, ни от того, чем сцену рисуют, поэтому
живёт в домене - им пользуются и виджет превью, и веб-фронт
"""

from __future__ import annotations

from typing import Tuple

#: Во столько единиц вписываем наибольшую сторону модели
TARGET_EXTENT = 2.0


#: Материалы призрака оригинала (custom_model_editor._custom_model_obj)
GHOST_PREFIX = "ghost:"


def compute_obj_bounds(obj_content: str) -> Tuple[float, float, float, float]:
    """
    Разбирает вершины OBJ и возвращает ``(cx, cy, cz, scale)``:

      * ``cx, cy, cz`` - центр ограничивающего параллелепипеда;
      * ``scale`` - во сколько раз сжать, чтобы наибольшая сторона стала
        TARGET_EXTENT

    Есть призрак оригинала (своя модель из импорта) - кадр по нему одному:
    своя модель лежит в OBJ ещё без подгонки, в метрах или в стороне, и
    кадр по всему выходил далеко и мимо. Подгонка ставит её на призрак

    У модели без вершин (пустой или битый файл) центр нулевой, масштаб 1:
    показать её всё равно нечем, и падать здесь незачем
    """
    verts, ghost, in_ghost = [], set(), False
    for line in obj_content.splitlines():
        if line.startswith("v "):
            parts = line.split()
            if len(parts) < 4:
                continue
            try:
                verts.append((float(parts[1]), float(parts[2]), float(parts[3])))
            except ValueError:
                continue
        elif line.startswith("usemtl "):
            in_ghost = line[7:].strip().startswith(GHOST_PREFIX)
        elif in_ghost and line.startswith("f "):
            for corner in line.split()[1:]:
                try:
                    i = int(corner.split("/")[0])
                except ValueError:
                    continue
                ghost.add(i - 1 if i > 0 else len(verts) + i)
    if ghost:
        verts = [verts[i] for i in sorted(ghost) if 0 <= i < len(verts)] or verts

    if not verts:
        return 0.0, 0.0, 0.0, 1.0
    xs, ys, zs = zip(*verts)

    cx = (min(xs) + max(xs)) / 2
    cy = (min(ys) + max(ys)) / 2
    cz = (min(zs) + max(zs)) / 2

    extent = max(max(xs) - min(xs), max(ys) - min(ys), max(zs) - min(zs))
    scale = (TARGET_EXTENT / extent) if extent > 0 else 1.0
    return cx, cy, cz, scale
