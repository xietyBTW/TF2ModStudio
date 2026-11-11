"""Простой режим: новые виды крутилок, быстрые правки, значение из игры"""

import unittest

from src.app.particle_simple_panel import effect_systems
from src.services import simple_params as sp
from tests.test_particle_params import _mod, _session, _system

PARAMS = {p.key: p for p in sp.SIMPLE_PARAMS}


def _by_key(rows):
    return {r['key']: r for r in rows}


class NewKindsTests(unittest.TestCase):
    def test_module_toggle_adds_with_seed_and_removes_all(self):
        s = _session({'sys': _system()})
        res = s.particles.set_particle_param('sys', 'follow', True)
        self.assertNotIn('error', res)
        ops = s.particles.pcf.systems_json()['sys']['operators']
        self.assertEqual([m['functionName'] for m in ops], ['Movement Lock to Control Point'])
        self.assertEqual(ops[0]['attrs']['control_point_number']['v'], 0)
        self.assertTrue(_by_key(s.particles.particle_params('sys'))['follow']['value'])
        # Два одинаковых модуля - выключатель убирает оба
        ops.append(_mod('Movement Lock to Control Point'))
        s.particles.set_particle_param('sys', 'follow', False)
        self.assertEqual(s.particles.pcf.systems_json()['sys']['operators'], [])
        self.assertFalse(_by_key(s.particles.particle_params('sys'))['follow']['value'])

    def test_turbulence_writes_both_vectors_in_one_call_each(self):
        s = _session({'sys': _system(forces=[_mod('random force')])})
        s.particles.set_particle_param('sys', 'turbulence', 40)
        attrs = s.particles.pcf.systems_json()['sys']['forces'][0]['attrs']
        self.assertEqual(attrs['max force']['v'], [40, 40, 40])
        self.assertEqual(attrs['min force']['v'], [-40, -40, -40])
        self.assertEqual(_by_key(s.particles.particle_params('sys'))['turbulence']['value'], 40)

    def test_percent_of_lifetime_is_stored_as_fraction(self):
        s = _session({'sys': _system(operators=[_mod('Color Fade')])})
        s.particles.set_particle_param('sys', 'color_fade_time', [25, 80])
        attrs = s.particles.pcf.systems_json()['sys']['operators'][0]['attrs']
        self.assertAlmostEqual(attrs['fade_start_time']['v'], 0.25)
        self.assertAlmostEqual(attrs['fade_end_time']['v'], 0.8)
        row = _by_key(s.particles.particle_params('sys'))['color_fade_time']
        self.assertEqual([round(v) for v in row['value']], [25, 80])

    def test_new_module_gets_seed_then_value(self):
        s = _session({'sys': _system()})
        s.particles.set_particle_param('sys', 'twist', 300)
        attrs = s.particles.pcf.systems_json()['sys']['forces'][0]['attrs']
        self.assertEqual(attrs['twist axis']['v'], [0.0, 0.0, 1.0])
        self.assertEqual(attrs['amount of force']['v'], 300)

    def test_choice_and_bool_are_read_as_such(self):
        s = _session({'sys': _system(renderers=[{
            'functionName': 'render_animated_sprites', 'name': 'r',
            'attrs': {'orientation_type': {'t': 'integer', 'v': 2},
                      'animation_fit_lifetime': {'t': 'bool', 'v': True}}}])})
        rows = _by_key(s.particles.particle_params('sys'))
        self.assertEqual(rows['orientation']['value'], 2)
        self.assertIs(rows['anim_fit']['value'], True)
        self.assertEqual([c['value'] for c in rows['orientation']['choices']], [0, 1, 2, 3])

    def test_targets_point_at_the_module_for_live_preview(self):
        s = _session({'sys': _system(operators=[
            _mod('Movement Basic', {'drag': 0.1}), _mod('Color Fade')])})
        rows = _by_key(s.particles.particle_params('sys'))
        self.assertEqual(rows['gravity']['targets'], [{
            'slot': 0, 'group': 'operators', 'index': 0, 'attr': 'gravity',
            'component': 2, 'scale': 1.0, 'type': 'vec3'}])
        self.assertEqual(rows['color_fade_time']['targets'][1]['index'], 1)
        self.assertEqual(rows['lifetime']['targets'], [])


class QuickEditTests(unittest.TestCase):
    def _effect(self):
        root = _system(initializers=[_mod('Radius Random', {'radius_min': 2.0, 'radius_max': 4.0})])
        root['children'] = [{'childName': 'kid'}]
        kid = _system(operators=[_mod('Movement Basic')])
        kid['attrs'] = {'radius': {'t': 'float', 'v': 10.0}}
        kid['operators'][0]['attrs']['gravity'] = {'t': 'vec3', 'v': [0.0, 0.0, -100.0]}
        return {'root': root, 'kid': kid, 'other': _system()}

    def test_scale_reaches_children_and_skips_strangers(self):
        s = _session(self._effect())
        res = s.particles.quick_particle_edit('root', 'scale', True)
        self.assertNotIn('error', res)
        sysj = s.particles.pcf.systems_json()
        rr = sysj['root']['initializers'][0]['attrs']
        self.assertAlmostEqual(rr['radius_min']['v'], 2.5)
        self.assertAlmostEqual(rr['radius_max']['v'], 5.0)
        self.assertAlmostEqual(sysj['kid']['attrs']['radius']['v'], 12.5)
        self.assertAlmostEqual(sysj['kid']['operators'][0]['attrs']['gravity']['v'][2], -125.0)
        self.assertEqual(sysj['other']['attrs'], {})

    def test_tempo_squares_accelerations(self):
        s = _session(self._effect())
        s.particles.quick_particle_edit('root', 'tempo', True)
        g = s.particles.pcf.systems_json()['kid']['operators'][0]['attrs']['gravity']['v'][2]
        self.assertAlmostEqual(g, -100.0 * 1.25 ** 2)

    def test_no_new_modules_and_unknown_kind(self):
        s = _session(self._effect())
        s.particles.quick_particle_edit('root', 'density', False)
        self.assertEqual(s.particles.pcf.added, [])
        self.assertIn('error', s.particles.quick_particle_edit('root', 'nope', True))

    def test_vector_axes_scale_each_on_its_own(self):
        """Снос вверх у хаотичной силы переживает «крупнее»"""
        force = _mod('random force')
        force['attrs'] = {'min force': {'t': 'vec3', 'v': [-5.0, -5.0, 0.0]},
                          'max force': {'t': 'vec3', 'v': [5.0, 5.0, 100.0]}}
        s = _session({'sys': _system(forces=[force])})
        s.particles.quick_particle_edit('sys', 'scale', True)
        attrs = s.particles.pcf.systems_json()['sys']['forces'][0]['attrs']
        self.assertEqual(attrs['min force']['v'], [-6.25, -6.25, 0.0])
        self.assertEqual(attrs['max force']['v'], [6.25, 6.25, 125.0])

    def test_missing_attributes_are_not_written(self):
        s = _session({'sys': _system(operators=[_mod('Movement Basic')])})
        res = s.particles.quick_particle_edit('sys', 'scale', True)
        self.assertIn('error', res)
        self.assertEqual(s.particles.pcf.writes, [])
        self.assertEqual(s.particles.pcf.systems_json()['sys']['attrs'], {})

    def test_small_integers_still_move(self):
        burst = {'functionName': 'emit_instantaneously', 'name': 'e',
                 'attrs': {'num_to_emit': {'t': 'integer', 'v': 1}}}
        s = _session({'sys': _system(emitters=[burst])})
        num = lambda: s.particles.pcf.systems_json()['sys']['emitters'][0]['attrs']['num_to_emit']['v']  # noqa: E731
        s.particles.quick_particle_edit('sys', 'density', True)
        self.assertEqual(num(), 2)
        s.particles.quick_particle_edit('sys', 'density', False)
        self.assertEqual(num(), 1)
        s.particles.quick_particle_edit('sys', 'density', False)
        self.assertEqual(num(), 1)            # залп не уходит в ноль

    def test_bounds_hold(self):
        rate = {'functionName': 'emit_continuously', 'name': 'e',
                'attrs': {'emission_rate': {'t': 'float', 'v': 900000.0}}}
        s = _session({'sys': _system(emitters=[rate])})
        s.particles.quick_particle_edit('sys', 'density', True)
        v = s.particles.pcf.systems_json()['sys']['emitters'][0]['attrs']['emission_rate']['v']
        self.assertEqual(v, PARAMS['spawn_rate'].input_max)

    def test_effect_systems_survives_cycles(self):
        systems = {'a': {'children': [{'childName': 'b'}]},
                   'b': {'children': [{'childName': 'a'}, {'childName': 'gone'}]}}
        self.assertEqual(sorted(effect_systems(systems.get, 'a')), ['a', 'b'])


class StockTests(unittest.TestCase):
    def test_stock_value_is_reported_when_the_game_knows_the_system(self):
        s = _session({'sys': _system(operators=[_mod('Movement Basic', {'drag': 0.5})])})
        stock = {'sys': _system(operators=[_mod('Movement Basic', {'drag': 0.1})])}
        s.particles.pcf.stock_systems = lambda root: stock
        s.particles.simple._root = lambda: 'C:/tf2'
        rows = _by_key(s.particles.particle_params('sys'))
        self.assertEqual(rows['drag']['value'], 0.5)
        self.assertEqual(rows['drag']['stock'], 0.1)
        self.assertIsNone(rows['lifetime']['stock'])

    def test_no_stock_key_without_game_version(self):
        s = _session({'sys': _system()})
        self.assertNotIn('stock', _by_key(s.particles.particle_params('sys'))['drag'])


class VectorScaleTests(unittest.TestCase):
    def test_whole_vector_scales_and_keeps_signs(self):
        mb = _mod('Movement Basic')
        mb['attrs']['gravity'] = {'t': 'vec3', 'v': [40.0, 0.0, -100.0]}
        force = _mod('random force')
        force['attrs'] = {'min force': {'t': 'vec3', 'v': [3.0, -5.0, 0.0]},
                          'max force': {'t': 'vec3', 'v': [8.0, 5.0, 0.0]}}
        s = _session({'sys': _system(operators=[mb], forces=[force])})
        s.particles.quick_particle_edit('sys', 'scale', True)
        sysj = s.particles.pcf.systems_json()['sys']
        self.assertEqual(sysj['operators'][0]['attrs']['gravity']['v'], [50.0, 0.0, -125.0])
        self.assertEqual(sysj['forces'][0]['attrs']['min force']['v'], [3.75, -6.25, 0.0])


if __name__ == '__main__':
    unittest.main()


class StatusCacheTests(unittest.TestCase):
    """Статусы «изменено» после точечной правки: пересчёт только правленой
    системы даёт то же, что полный пересчёт"""

    def setUp(self):
        import copy

        self.s = _session({'a': _system(operators=[_mod('Movement Basic', {'drag': 0.1})]),
                           'b': _system(operators=[_mod('Movement Basic', {'drag': 0.2})])})
        ed = self.s.particles
        pcf = ed.pcf
        pcf.snapshot = lambda: copy.deepcopy(pcf._systems)
        self.stock = copy.deepcopy(pcf._systems)
        ed._stock_systems = lambda: self.stock
        ed.history.reset(pcf.snapshot())
        self.full_calls = 0
        real = pcf.systems_json

        def counting():
            self.full_calls += 1
            return real()
        pcf.systems_json = counting
        pcf.system_json = lambda name: real().get(name)

    def test_incremental_matches_full(self):
        ed = self.s.particles
        first = ed.set_particle_param('a', 'drag', 0.5)
        self.assertEqual(first['diff'], {'a': 'changed', 'b': 'same'})
        calls = self.full_calls
        second = ed.set_particle_param('b', 'drag', 0.7)
        self.assertEqual(second['diff'], {'a': 'changed', 'b': 'changed'})
        self.assertEqual(self.full_calls, calls)          # весь файл не строили
        back = ed.set_particle_param('a', 'drag', 0.1)
        self.assertEqual(back['diff'], {'a': 'same', 'b': 'changed'})

    def test_foreign_step_forces_full_recount(self):
        ed = self.s.particles
        ed.set_particle_param('a', 'drag', 0.5)
        # Правка мимо простого режима: шаг истории без пересчёта статусов
        ed.pcf._systems['b']['operators'][0]['attrs']['drag']['v'] = 0.9
        ed._history_commit()
        res = ed.set_particle_param('a', 'drag', 0.6)
        self.assertEqual(res['diff'], {'a': 'changed', 'b': 'changed'})
