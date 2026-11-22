"""Поиск с опечатками: правило Algolia и то, что точное всегда выше"""

import unittest

from src.shared.text_search import TypoIndex, find, prefix_typos, typo_budget


class TypoBudgetTest(unittest.TestCase):
    def test_short_words_must_be_exact(self):
        self.assertEqual(typo_budget('bat'), 0)
        self.assertEqual(typo_budget('fedr'), 1)
        self.assertEqual(typo_budget('scatergun'), 2)


class PrefixTyposTest(unittest.TestCase):
    def test_missing_letter(self):
        self.assertEqual(prefix_typos('fedra', 'fedora', 1), 1)

    def test_tail_of_word_is_free(self):
        self.assertEqual(prefix_typos('fedra', 'fedoras', 1), 1)

    def test_swapped_letters_cost_one(self):
        self.assertEqual(prefix_typos('fedroa', 'fedora', 1), 1)

    def test_too_far_stops_at_limit(self):
        self.assertEqual(prefix_typos('scout', 'scatter', 1), 2)


class FindTest(unittest.TestCase):
    def setUp(self):
        self.index = TypoIndex(['Fancy Fedora', 'Scattergun', 'Burning Flames',
                                'superrare_burning1', 'Scout'])

    def test_exact_needs_no_typos(self):
        self.assertEqual(find(['fedora'], 'fancy fedora', self.index), 0)

    def test_typo_found_and_counted(self):
        self.assertEqual(find(['fedra'], 'fancy fedora', self.index), 1)
        self.assertEqual(find(['scatergun'], 'scattergun', self.index), 1)

    def test_typo_inside_glued_text(self):
        # Текст частиц склеен без разделителей, слово ищется подстрокой
        self.assertEqual(find(['flams'], 'superrareburning1 burningflames', self.index), 1)

    def test_short_word_has_no_typos(self):
        self.assertIsNone(find(['fdr'], 'fancy fedora', self.index))

    def test_unrelated_word_misses(self):
        self.assertIsNone(find(['scout'], 'scattergun', self.index))

    def test_every_word_must_match(self):
        self.assertIsNone(find(['fedra', 'helmet'], 'fancy fedora', self.index))

    def test_without_index_only_exact(self):
        self.assertIsNone(find(['fedra'], 'fancy fedora', None))


if __name__ == '__main__':
    unittest.main()
