"""
Правки VMT - в работе открытого предмета, а не в общей папке

Раньше правка лежала файлом по имени материала и всплывала у любого предмета с
этим материалом: стоковый обрез из каталога открывался с чужим эффектом крита.
Теперь сервис читает и пишет правки предмета (VmtEdits), а сборке отдаёт копию
файла; старые файлы переезжают в предмет один раз
"""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from src.domain.preview.session import PreviewSession, has_real_edits
from src.domain.preview.vmt_edits import VmtEdits
from src.services.edited_vmt_service import EditedVMTService as Vmt


class EditedVMTServiceTests(unittest.TestCase):
    def setUp(self):
        self.was = Vmt._live
        self.item = PreviewSession()
        Vmt.bind(lambda: self.item.vmt)

    def tearDown(self):
        Vmt.bind(self.was)

    def test_save_get_and_delete(self):
        Vmt.save_edited_vmt("c_test", '"UnlitGeneric" {}')
        self.assertTrue(Vmt.has_edited_vmt("c_test"))
        self.assertEqual(Vmt.get_text("c_test"), '"UnlitGeneric" {}')
        path = Vmt.get_edited_vmt("c_test")
        self.assertEqual(Path(path).read_text(encoding="utf-8"), '"UnlitGeneric" {}')
        self.assertTrue(Vmt.delete_edited_vmt("c_test"))
        self.assertFalse(Vmt.has_edited_vmt("c_test"))
        self.assertIsNone(Vmt.get_edited_vmt("c_test"))

    def test_build_finds_the_edit_of_a_dotted_card(self):
        # Карточка своей модели `Material.001`, а сборка знает материал так,
        # как его собирает studiomdl: `material_001`
        Vmt.save_edited_vmt("Material.001", '"VertexLitGeneric" {}')
        self.assertEqual(Path(Vmt.get_edited_vmt("material_001")).read_text(encoding="utf-8"),
                         '"VertexLitGeneric" {}')
        self.assertIsNone(Vmt.get_edited_vmt("material_002"))

    def test_original_backup_roundtrip_and_cleanup(self):
        self.assertFalse(Vmt.has_original_backup("c_test"))
        Vmt.save_original_backup("c_test", "game original")
        self.assertEqual(Vmt.read_original_backup("c_test"), "game original")
        self.assertFalse(Vmt.has_edited_vmt("c_test"))
        Vmt.save_edited_vmt("c_test", "edited")
        Vmt.delete_edited_vmt("c_test")
        self.assertFalse(Vmt.has_original_backup("c_test"))

    def test_edit_belongs_to_the_item(self):
        """Работа, сброс и другой предмет - как у текстур"""
        Vmt.save_original_backup("c_test", "game")
        Vmt.save_edited_vmt("c_test", "edited")
        edits = self.item.user_edits()
        self.assertTrue(has_real_edits(edits))
        self.assertEqual(edits["vmt_edits"], {"c_test": "edited"})

        self.item.forget_user_edits()
        self.assertFalse(Vmt.has_edited_vmt("c_test"))      # «Забыть правки»
        self.item.apply_user_edits(edits)
        self.assertEqual(Vmt.get_text("c_test"), "edited")  # «Вернуть правки»
        self.assertEqual(Vmt.read_original_backup("c_test"), "game")

        self.item.begin_item("c_other", "scout_c_other")
        self.assertFalse(Vmt.has_edited_vmt("c_test"))      # другой предмет - игровой VMT

    def test_build_reads_its_snapshot_not_the_open_item(self):
        Vmt.save_edited_vmt("c_test", "for the build")
        snap = Vmt.snapshot()
        self.item.begin_item("c_other", "scout_c_other")     # человек открыл другое
        with Vmt.use(snap):
            self.assertEqual(Vmt.get_text("c_test"), "for the build")
        self.assertIsNone(Vmt.get_text("c_test"))

    def test_case_of_the_key_does_not_matter(self):
        """Файлами правки находились без учёта регистра, сборка спрашивает
        то именем карточки, то именем из модели"""
        Vmt.save_original_backup("C_Test", "game")
        Vmt.save_edited_vmt("C_Test", "edited")
        self.assertEqual(Vmt.get_text("c_test"), "edited")
        Vmt.save_edited_vmt("c_test", "again")
        self.assertEqual(self.item.vmt.texts, {"C_Test": "again"})   # не вторая правка
        self.assertEqual(Vmt.read_original_backup("c_test"), "game")
        self.assertTrue(Vmt.delete_edited_vmt("c_test"))
        self.assertEqual((self.item.vmt.texts, self.item.vmt.origs), ({}, {}))

    def test_hat_styles_share_the_vmt_edit(self):
        """Файл материала у стилей шапки общий: снимок стиля - без VMT, а
        живая правка переходит на новый стиль поверх старой"""
        Vmt.save_edited_vmt("hat", "for all styles")
        snap = VmtEdits.without(self.item.user_edits())
        self.assertNotIn("vmt_edits", snap)
        old = VmtEdits({"hat": "old", "band": "old"})
        self.assertEqual(self.item.vmt.merged(old).texts,
                         {"hat": "for all styles", "band": "old"})

    def test_kept_legacy_file_when_the_work_is_not_written(self):
        with tempfile.TemporaryDirectory() as tmp:
            Path(tmp, "c_test.vmt").write_text("old edit", encoding="utf-8")
            with patch.object(Vmt, "EDITED_VMT_DIR", tmp):
                Vmt.adopt_legacy(["c_test"], remove=False)
                self.assertTrue(Path(tmp, "c_test.vmt").exists())
        self.assertEqual(Vmt.get_text("c_test"), "old edit")

    def test_old_shared_edit_moves_into_the_item_once(self):
        with tempfile.TemporaryDirectory() as tmp:
            Path(tmp, "c_test.vmt").write_text("old edit", encoding="utf-8")
            Path(tmp, "c_test.orig").write_text("game", encoding="utf-8")
            with patch.object(Vmt, "EDITED_VMT_DIR", tmp):
                self.assertEqual(Vmt.adopt_legacy(["c_test", "c_none"]), {"c_test": "old edit"})
                self.assertEqual(Vmt.read_original_backup("c_test"), "game")
                self.assertEqual(list(Path(tmp).iterdir()), [])     # больше не всплывёт
                self.assertEqual(Vmt.adopt_legacy(["c_test"]), {})


def test_unbound_service_has_no_edits():
    was = Vmt._live
    Vmt.bind(None)
    try:
        assert Vmt.get_text("c_test") is None
        assert Vmt.snapshot().texts == {}
        assert isinstance(Vmt.snapshot(), VmtEdits)
    finally:
        Vmt.bind(was)


if __name__ == "__main__":
    unittest.main()
