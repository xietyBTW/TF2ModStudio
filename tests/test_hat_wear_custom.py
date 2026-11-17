"""Сцена «На персонаже» у шапки показывает свою модель, а не игровую"""

import unittest
from unittest.mock import patch

from src.app.session import AppSession


class HatWearCustomModelTests(unittest.TestCase):
    def test_custom_model_reaches_the_scene(self):
        s = AppSession()
        s._mode = 'hat'
        s._hat_models = {'soldier': 'models/player/items/soldier/x.mdl'}
        s.preview.custom_smd_path = 'C:/work/my_hat.smd'
        s.preview.custom_keep_materials = True
        with patch.object(type(s), 'tf2_paths', staticmethod(
                lambda: {'root': 'r', 'misc_vpk': 'm', 'textures_vpk': 't'})), \
                patch.object(s, '_hat_catalog_item', return_value=None), \
                patch.object(s.taunt, 'load_wear') as load:
            self.assertEqual(s.load_wear(), {'started': True})
        kw = load.call_args.kwargs
        self.assertEqual(kw['custom_smd'], 'C:/work/my_hat.smd')
        self.assertTrue(kw['custom_keep'])


if __name__ == '__main__':
    unittest.main()
