"""Персонаж и реквизит, что стоит рядом, - одной сценой"""

import math
import unittest

from src.services.taunt_scene_merge import PREFIX, add_held_prop, merge_world_prop


def _scene(bone_names, kind, times, rotation=0.0, scale=1.0):
    return {
        'rootRotationX': rotation,
        'bones': [{'name': n, 'parent': i - 1, 'position': [0, 0, 0],
                   'quaternion': [0, 0, 0, 1]} for i, n in enumerate(bone_names)],
        'parts': [{'kind': kind, 'skinIndex': [0, 1, 0, 0], 'materials': [kind]}],
        'clip': {'name': kind, 'times': times, 'duration': times[-1],
                 'tracks': [{'bone': 1, 'name': bone_names[1], 'positions': [],
                             'quaternions': []}]},
        'weaponMaterials': [kind],
        'bounds': {'cx': 0, 'cy': 0, 'cz': 0, 'scale': scale},
    }


class MergeWorldPropTests(unittest.TestCase):
    def setUp(self):
        self.player = _scene(['bip_pelvis', 'bip_spine'], 'arms', [0.0, 1.0], rotation=-1.57)
        self.prop = _scene(['root', 'seat'], 'arms', [0.0, 0.5, 2.0], scale=3.0)
        self.merged = merge_world_prop(self.player, self.prop)

    def test_prop_bones_hang_under_their_own_root(self):
        bones = self.merged['bones']
        self.assertEqual([b['name'] for b in bones],
                         ['bip_pelvis', 'bip_spine', PREFIX + 'root', PREFIX + 'root', PREFIX + 'seat'])
        self.assertEqual([b['parent'] for b in bones], [-1, 0, -1, 2, 3])

    def test_prop_mesh_points_at_shifted_bones(self):
        prop_part = self.merged['parts'][1]
        self.assertEqual(prop_part['kind'], 'prop')
        self.assertEqual(prop_part['skinIndex'], [3, 4, 3, 3])
        self.assertEqual(self.merged['parts'][0]['skinIndex'], [0, 1, 0, 0])

    def test_prop_track_keeps_its_own_frames(self):
        tracks = self.merged['clip']['tracks']
        self.assertEqual(tracks[1]['bone'], 4)
        self.assertEqual(tracks[1]['name'], PREFIX + 'seat')
        self.assertEqual(tracks[1]['times'], [0.0, 0.5, 2.0])
        self.assertNotIn('times', tracks[0])
        self.assertEqual(self.merged['clip']['duration'], 2.0)

    def test_root_turns_prop_into_its_own_axes(self):
        quat = self.merged['bones'][2]['quaternion']
        self.assertAlmostEqual(quat[3], 0.7073, places=3)      # пол-оборота от 1.57
        self.assertEqual(self.merged['weaponMaterials'], ['arms'])
        self.assertEqual(self.merged['bounds']['scale'], 3.0)

    def test_held_prop_joins_the_scene_with_a_weapon(self):
        """Оружие в руках, реквизит рядом с ним: правится только реквизит, а
        AE_WPN_HIDE его не касается"""
        with_weapon = _scene(['bip_pelvis', 'bip_spine'], 'weapon', [0.0, 1.0])
        with_weapon['parts'].insert(0, {'kind': 'arms', 'materials': ['body']})
        held = _scene(['bip_pelvis', 'bip_spine'], 'weapon', [0.0, 1.0])
        held['weaponMaterials'] = ['towel']
        merged = add_held_prop(with_weapon, held)
        self.assertEqual([p['kind'] for p in merged['parts']], ['arms', 'weapon', 'prop'])
        self.assertEqual(merged['weaponMaterials'], ['towel'])
        self.assertEqual(merged['bones'], with_weapon['bones'])

    def test_bone_names_are_safe_for_three_track_paths(self):
        """three.js читает `a:b.position` как путь: с «:» или «.» в имени кости
        дорожка реквизита молча пропадала, и он стоял в позе покоя"""
        prop = _scene(['Root', 'Pot.JNT'], 'arms', [0.0, 1.0])
        merged = merge_world_prop(self.player, prop)
        names = [b['name'] for b in merged['bones']] + [t['name'] for t in merged['clip']['tracks']]
        self.assertFalse([n for n in names if any(c in n for c in '[].:/ ')])

    def test_prop_vertices_turn_with_its_root(self):
        """Поворот корня входит в позу покоя - вершины поворачиваются тоже,
        иначе стол пулемётчика лежал на боку"""
        prop = _scene(['Root', 'seat'], 'arms', [0.0, 1.0], rotation=-math.pi / 2)
        prop['parts'][0]['positions'] = [0.0, 0.0, 10.0]
        prop['parts'][0]['normals'] = [0.0, 0.0, 1.0]
        player = _scene(['bip_pelvis', 'bip_spine'], 'arms', [0.0, 1.0], rotation=0.0)
        part = merge_world_prop(player, prop)['parts'][1]
        self.assertEqual([round(v, 3) for v in part['positions']], [0.0, 10.0, 0.0])
        self.assertEqual([round(v, 3) for v in part['normals']], [0.0, 1.0, 0.0])

    def test_missing_half_gives_the_other(self):
        self.assertIs(merge_world_prop(self.player, None), self.player)
        self.assertIs(merge_world_prop(None, self.prop), self.prop)


if __name__ == '__main__':
    unittest.main()
