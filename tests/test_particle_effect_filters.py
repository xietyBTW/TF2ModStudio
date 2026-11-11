"""Фильтры списка эффектов игры: источник без обрезки и разделы необычных"""

import unittest

from src.app.particle_effects_catalog import EffectCatalog


def row(system, kinds, category='', name='', labels=()):
    return {'system': system, 'file': 'particles/x.pcf', 'name': name,
            'root': '', 'category': category, 'category_name': category,
            'kinds': list(kinds), 'labels': list(labels),
            'blob': system, 'keys': [system]}


class EffectFiltersTest(unittest.TestCase):
    def setUp(self):
        rows = ([row(f'hat{i}', ['unusual'], 'cosmetic', f'Hat {i}') for i in range(900)]
                + [row('gun_hot', ['unusual'], 'weapon', 'Hot')]
                + [row('dance', ['unusual'], 'taunt', 'Dance')]
                + [row('inner', ['unusual'])]
                + [row('flame', ['weapon'], labels=['Flamethrower'])])
        self.ed = EffectCatalog(host=None)
        self.ed._children = {}
        self.ed._effect_rows = lambda lang: (rows, True)

    def test_source_list_is_not_cut(self):
        res = self.ed.particle_effects('', 'unusual')
        self.assertEqual(res['total'], 903)
        self.assertEqual(len(res['items']), 903)
        self.assertIn('gun_hot', [it['system'] for it in res['items']])

    def test_categories_count_before_the_pick(self):
        res = self.ed.particle_effects('', 'unusual', category='taunt')
        self.assertEqual([it['system'] for it in res['items']], ['dance'])
        counts = {c['key']: c['count'] for c in res['categories']}
        self.assertEqual(counts, {'cosmetic': 900, 'taunt': 1, 'weapon': 1, 'unnamed': 1})

    def test_unusuals_go_by_category_order(self):
        res = self.ed.particle_effects('', 'unusual')
        order = [it['category'] for it in res['items']]
        self.assertEqual(order[-3:], ['taunt', 'weapon', ''])

    def test_other_sources_have_no_categories(self):
        res = self.ed.particle_effects('', 'weapon')
        self.assertEqual(res['categories'], [])
        self.assertEqual([it['system'] for it in res['items']], ['flame'])

    def test_search_is_still_paged(self):
        res = self.ed.particle_effects('hat', 'unusual')
        self.assertEqual(len(res['items']), EffectCatalog.EFFECTS_PAGE)
        self.assertEqual(res['total'], 900)


class LazyKidsTest(unittest.TestCase):
    """Дочерние строки приходят по раскрытию, а не в каждом ответе списка"""

    def setUp(self):
        kid = row('spark', ['unusual'])
        kid['root'] = 'hat'
        rows = [row('hat', ['unusual'], 'cosmetic', 'Hat'), kid]
        self.ed = EffectCatalog(host=None)
        self.ed._children = {'hat': ['spark']}
        self.ed._effect_rows = lambda lang: (rows, True)

    def test_list_carries_count_not_rows(self):
        item = self.ed.particle_effects('', 'unusual')['items'][0]
        self.assertEqual((item['kids'], item['kids_n']), ([], 1))
        self.assertEqual([k['system'] for k in self.ed.effect_kids('hat', '', 'unusual')],
                         ['spark'])

    def test_search_keeps_kids_inline(self):
        item = self.ed.particle_effects('spark', '')['items'][0]
        self.assertEqual([k['system'] for k in item['kids']], ['spark'])


class WeaponVariantsTest(unittest.TestCase):
    def test_suffixed_systems_go_under_the_weapon_unusual(self):
        from src.app.particle_effects_catalog import with_weapon_variants

        index = {s: 'particles/x.pcf' for s in (
            'weapon_unusual_hot_rocketlauncher', 'weapon_unusual_hot_rocketlauncher_vm',
            'hot_rl_sparks', 'weapon_unusual_hotdog', 'superrare_burning1')}
        roots = {'hot_rl_sparks': 'weapon_unusual_hot_rocketlauncher'}
        unusuals = [{'system': 'weapon_unusual_hot', 'category': 'weapon'},
                    {'system': 'superrare_burning1', 'category': 'cosmetic'}]
        out = with_weapon_variants(index, roots, unusuals)
        self.assertEqual(out, {
            'weapon_unusual_hot_rocketlauncher': 'weapon_unusual_hot',
            'weapon_unusual_hot_rocketlauncher_vm': 'weapon_unusual_hot',
            'hot_rl_sparks': 'weapon_unusual_hot'})


if __name__ == '__main__':
    unittest.main()
