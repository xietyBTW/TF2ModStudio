"""
Экспорт текстуры одной карточки: что сохраняется («как на карточке» или
оригинал игры), под каким именем и в каком формате
"""

import io
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from PIL import Image

from src.app.tools_editor import ToolsEditor
from src.domain.preview.texture_state import PreviewTextureState
from src.services import texture_export
from src.services.particle_editor import materials as particle_materials
from src.shared.constants import Team


def _png(path: Path, color) -> str:
    Image.new('RGBA', (8, 8), color).save(path)
    return str(path)


class ExportImageTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def test_name_from_material_path(self):
        self.assertEqual(texture_export.file_stem('effects/glow.vmt'), 'glow')
        self.assertEqual(texture_export.file_stem('c_scattergun'), 'c_scattergun')
        self.assertEqual(texture_export.file_stem('a:b?'), 'a_b_')
        self.assertEqual(texture_export.file_stem(''), 'texture')

    def test_second_export_does_not_overwrite(self):
        src = _png(self.dir / 'in.png', (255, 0, 0, 128))
        first = texture_export.export_image(src, self.dir / 'out', 'gun', 'PNG')
        second = texture_export.export_image(src, self.dir / 'out', 'gun', 'PNG')
        self.assertEqual((first.name, second.name), ('gun.png', 'gun_2.png'))

    def test_formats_and_alpha(self):
        src = _png(self.dir / 'in.png', (255, 0, 0, 128))
        png = texture_export.export_image(src, self.dir, 'a', 'PNG')
        jpg = texture_export.export_image(src, self.dir, 'a', 'JPG')
        tga = texture_export.export_image(src, self.dir, 'a', 'TGA')
        # VTF в настройках - всё равно картинка для графического редактора
        vtf = texture_export.export_image(src, self.dir, 'b', 'VTF')
        self.assertEqual(Image.open(png).getpixel((0, 0)), (255, 0, 0, 128))
        self.assertEqual(Image.open(jpg).mode, 'RGB')
        self.assertEqual(Image.open(tga).getpixel((0, 0))[3], 128)
        self.assertEqual(vtf.suffix, '.png')

    def test_png_bytes_source(self):
        buf = io.BytesIO()
        Image.new('RGBA', (4, 4), (0, 255, 0, 255)).save(buf, format='PNG')
        out = texture_export.export_image(buf.getvalue(), self.dir, 'effects/x.vmt', 'PNG')
        self.assertEqual(out.name, 'x.png')


class OriginalCardTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        d = Path(self._tmp.name)
        self.stock = _png(d / 'stock.png', (10, 10, 10, 255))
        self.own = _png(d / 'own.png', (200, 0, 0, 255))
        self.gold = _png(d / 'gold.png', (255, 200, 0, 255))
        self.t = PreviewTextureState(material_names=['gun'], main_material='gun')
        self.t.vpk_red_tex_map = {'gun': self.stock}

    def tearDown(self):
        self._tmp.cleanup()

    def test_original_ignores_own_picture(self):
        self.t.textures[Team.RED]['gun'] = self.own
        self.assertEqual(self.t.resolve_card('gun'), self.own)
        self.assertEqual(self.t.original_card('gun'), self.stock)

    def test_variant_original_is_its_game_frame(self):
        self.t.australium_mat_name = 'gun_gold'
        self.t.australium_frame = self.gold
        self.assertEqual(self.t.original_card('gun_gold'), self.gold)


class _Host:
    """Сеанс ровно настолько, насколько его трогает экспорт карточки"""

    def __init__(self, folder, shown, textures):
        self.preview = SimpleNamespace(textures=textures,
                                       visible_textures=lambda: shown)
        self._folder = folder

    def _painted(self, textures):
        return textures

    def _export_settings(self):
        return self._folder, 'PNG'


class CardExportTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self._tmp.name)
        self.stock = _png(self.dir / 'stock.png', (10, 10, 10, 255))
        self.own = _png(self.dir / 'own.png', (200, 0, 0, 255))
        textures = PreviewTextureState(material_names=['gun'], main_material='gun')
        textures.vpk_red_tex_map = {'gun': self.stock}
        self.tools = ToolsEditor(_Host(str(self.dir / 'export'), {'gun': self.own}, textures))

    def tearDown(self):
        self._tmp.cleanup()

    def test_as_on_card(self):
        res = self.tools.export_card_texture('gun')
        self.assertEqual(res['name'], 'gun.png')
        self.assertEqual(Image.open(res['path']).getpixel((0, 0))[:3], (200, 0, 0))

    def test_original_prefers_unpainted_source(self):
        # Красящаяся вещь: у показанного оригинала рядом лежит некрашеный
        _png(self.dir / 'stock.png.raw.png', (0, 0, 0, 40))
        res = self.tools.export_card_texture('gun', original=True)
        self.assertEqual(res['name'], 'gun_original.png')
        self.assertEqual(Image.open(res['path']).getpixel((0, 0))[3], 40)

    def test_single_material_item_is_named_after_the_item(self):
        self.tools._host.preview.visible_textures = lambda: {'__single__': self.own}
        self.tools._host.preview.weapon_key = 'c_scattergun'
        self.assertEqual(self.tools.export_card_texture('__single__')['name'],
                         'c_scattergun.png')

    def test_card_without_texture(self):
        self.assertIn('error', self.tools.export_card_texture('nothing'))

    def test_changed_cards_only_where_not_the_game_original(self):
        # Своя картинка - оригинал есть смысл экспортировать отдельно
        self.assertEqual(self.tools.changed_cards({'gun': self.own}), ['gun'])
        # На карточке и так игровой оригинал - второго пункта меню нет
        self.assertEqual(self.tools.changed_cards({'gun': self.stock}), [])
        # Оригинала у карточки нет вовсе - предлагать нечего
        self.assertEqual(self.tools.changed_cards({'nothing': self.own}), [])


class ParticleMaterialTests(unittest.TestCase):
    def test_own_picture_and_original(self):
        buf = io.BytesIO()
        Image.new('RGBA', (2, 2), (1, 2, 3, 4)).save(buf, format='PNG')
        import base64
        url = 'data:image/png;base64,' + base64.b64encode(buf.getvalue()).decode()
        pcf = SimpleNamespace(_custom_material_info={'effects/glow.vmt': {'dataUrl': url}})
        own = particle_materials.material_png(pcf, 'C:/no_tf2', 'effects/glow.vmt')
        self.assertEqual(own, buf.getvalue())
        # Оригинал ищется в игре, а её тут нет: свою картинку он не подменяет
        self.assertIsNone(particle_materials.material_png(
            pcf, 'C:/no_tf2', 'effects/glow.vmt', original=True))


if __name__ == '__main__':
    unittest.main()
