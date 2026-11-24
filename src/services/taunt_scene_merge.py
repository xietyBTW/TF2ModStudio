"""
Насмешка с реквизитом, который стоит рядом, а не в руках

Родео, стул инженера, перевёрнутый стол: в игре реквизит - отдельная модель
со своим скелетом и своей сценой (`custom_taunt_prop_scene_per_class`), а
персонаж в это время играет свою последовательность. Общих костей у них нет,
поэтому сажать реквизит в руку нечем, и раньше в кадре оставался один
реквизит

Здесь две готовые сцены `viewmodel_animation.build_scene` сливаются в одну:
кости реквизита встают под свой корень, повёрнутый на разницу осей моделей,
а его дорожки идут со своими кадрами (`times` у дорожки)
"""

from __future__ import annotations

import math
import re
from typing import Optional

from src.services.viewmodel_animation import quaternion_from_euler

#: Приставка к костям реквизита: имена у двух скелетов могут совпасть, а клип
#: находит кость по имени. Без «:» и «.»: three.js (PropertyBinding) читает
#: `prop:Root.position` как путь, кость не находит, и реквизит стоял в позе
#: покоя - стол на месте пулемётчика, кресло сразу разобранным
PREFIX = 'prop__'
_RESERVED = re.compile(r'[\[\].:/\s]')


def _bone_name(name: str) -> str:
    return PREFIX + _RESERVED.sub('_', name)
#: Вид части-реквизита. Не «weapon»: события AE_WPN_HIDE прячут оружие в
#: руках, а реквизит со своей сценой на них не смотрит
PROP_KIND = 'prop'


def add_held_prop(scene: Optional[dict], held: Optional[dict]) -> Optional[dict]:
    """Реквизит из сцены `held` в сцену с оружием в руках

    Скелет у обеих сцен один - персонажа, порядок костей тот же, поэтому части
    переносятся как есть. Править человек может только реквизит
    """
    if not scene or not held:
        return scene or held
    props = [{**part, 'kind': PROP_KIND} for part in held['parts']
             if part.get('kind') == 'weapon']
    # Порядок костей общий, но неподвижная кость начала координат
    # (viewmodel_animation.ORIGIN_BONE) есть только там, где она нужна
    bones = max(scene['bones'], held['bones'], key=len)
    return {**scene, 'bones': bones, 'parts': list(scene['parts']) + props,
            'weaponMaterials': held.get('weaponMaterials') or []}


def merge_world_prop(player: Optional[dict], prop: Optional[dict]) -> Optional[dict]:
    """Сцена персонажа плюс реквизит в той же точке со своей анимацией"""
    if not player or not prop:
        return player or prop
    bones = list(player['bones'])
    root_at = len(bones)
    offset = root_at + 1
    # Группу сцены поворачивает ось персонажа, а у реквизита она своя: у
    # персонажа `$upaxis Y`, у стула обычный Source Z-вверх
    turn = float(prop.get('rootRotationX') or 0.0) - float(player.get('rootRotationX') or 0.0)
    bones.append({'name': PREFIX + 'root', 'parent': -1, 'position': [0.0, 0.0, 0.0],
                  'quaternion': list(quaternion_from_euler((turn, 0.0, 0.0)))})
    for bone in prop['bones']:
        parent = bone.get('parent', -1)
        bones.append({**bone, 'name': _bone_name(bone['name']),
                      'parent': parent + offset if parent >= 0 else root_at})

    parts = list(player['parts'])
    for part in prop['parts']:
        # Поворот корня входит и в позу покоя, по которой three.js считает
        # обратные матрицы, поэтому вершины поворачиваются вместе с ним: иначе
        # он применялся «туда и обратно» неверно, и стол лежал на боку
        parts.append({**part, 'kind': PROP_KIND,
                      'positions': _turned(part.get('positions') or [], turn),
                      'normals': _turned(part.get('normals') or [], turn),
                      'skinIndex': [i + offset for i in part.get('skinIndex') or []]})

    return {**player, 'bones': bones, 'parts': parts,
            'clip': _merge_clips(player.get('clip'), prop.get('clip'), offset),
            'weaponMaterials': prop.get('weaponMaterials') or [],
            'bounds': _merge_bounds(player.get('bounds'), prop.get('bounds'))}


def _turned(flat: list, angle: float) -> list:
    """Тройки x, y, z, повёрнутые вокруг X - тем же поворотом, что у корня"""
    if not angle:
        return list(flat)
    cos, sin = math.cos(angle), math.sin(angle)
    out = list(flat)
    for i in range(0, len(out) - 2, 3):
        y, z = out[i + 1], out[i + 2]
        out[i + 1] = round(y * cos - z * sin, 4)
        out[i + 2] = round(y * sin + z * cos, 4)
    return out


def _merge_clips(own: Optional[dict], other: Optional[dict], offset: int) -> Optional[dict]:
    if not other:
        return own
    tracks = [{**track, 'bone': track['bone'] + offset,
               'name': _bone_name(track['name']), 'times': other['times']}
              for track in other.get('tracks') or []]
    if not own:
        return {**other, 'tracks': tracks}
    return {**own, 'tracks': list(own.get('tracks') or []) + tracks,
            'duration': max(own.get('duration') or 0.0, other.get('duration') or 0.0)}


def _merge_bounds(own: Optional[dict], other: Optional[dict]) -> Optional[dict]:
    """Центр по персонажу, размер по большему: стол шире пулемётчика"""
    if not own or not other:
        return own or other
    return {**own, 'scale': max(own.get('scale') or 0.0, other.get('scale') or 0.0)}
