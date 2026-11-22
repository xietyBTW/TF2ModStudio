"""Миниатюры War Paint и недавно нанесённые"""

import os
import tempfile
import unittest
from types import SimpleNamespace

from src.services import paintkit_thumbs as pt


class RecentTests(unittest.TestCase):
    def test_new_one_goes_first_without_repeats(self):
        self.assertEqual(pt.remember([3, 1, 2], 2), [2, 3, 1])
        self.assertEqual(pt.remember(None, 7), [7])
        self.assertEqual(len(pt.remember(list(range(10)), 99)), pt.RECENT)

    def test_junk_from_config_is_dropped(self):
        self.assertEqual(pt.recent([1, 'x', True, None, 2.5, 4]), [1, 4])
        self.assertEqual(pt.recent({'a': 1}), [])


class ThumbTests(unittest.TestCase):
    def test_no_recipe_no_thumb(self):
        defs = SimpleNamespace(kits={})
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(pt.thumb(defs, 1, 2, None, tmp), '')

    def test_ready_thumb_is_not_rebuilt(self):
        with tempfile.TemporaryDirectory() as tmp:
            ready = os.path.join(tmp, '5_6_64.png')
            open(ready, 'wb').close()
            # defs без рецептов: дошло бы до сборки - упало бы
            self.assertEqual(pt.thumb(None, 5, 6, None, tmp), ready)


if __name__ == '__main__':
    unittest.main()
