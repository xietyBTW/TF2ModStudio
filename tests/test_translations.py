"""
Тесты целостности словарей переводов

Цель - не дать языкам разъехаться: если в один язык добавили ключ, а в другой
забыли, UI начнёт показывать английский fallback (или KeyError при self.t[key]).
Тест ловит это до рантайма
"""

import unittest

from src.data.translations import TRANSLATIONS


class TranslationsParityTests(unittest.TestCase):
    def test_languages_present(self):
        self.assertIn("ru", TRANSLATIONS)
        self.assertIn("en", TRANSLATIONS)

    def test_ru_en_key_parity(self):
        ru = set(TRANSLATIONS["ru"])
        en = set(TRANSLATIONS["en"])
        only_ru = ru - en
        only_en = en - ru
        self.assertEqual(
            only_ru, set(),
            f"Ключи есть только в 'ru', нет в 'en': {sorted(only_ru)}",
        )
        self.assertEqual(
            only_en, set(),
            f"Ключи есть только в 'en', нет в 'ru': {sorted(only_en)}",
        )

    def test_no_empty_values(self):
        for lang, mapping in TRANSLATIONS.items():
            for key, value in mapping.items():
                self.assertIsInstance(value, str, f"{lang}['{key}'] не строка")
                self.assertTrue(value.strip(), f"{lang}['{key}'] пустая строка")

    def test_tab_keys_exist(self):
        # Без ключей вкладки держались бы на fallback в .get(), и русская
        # вкладка оружия показывалась как "Weapons"
        for key in ("tab_weapons", "tab_hats"):
            self.assertIn(key, TRANSLATIONS["ru"])
            self.assertIn(key, TRANSLATIONS["en"])


if __name__ == "__main__":
    unittest.main()


def test_tr_falls_back_and_formats():
    from src.data.translations import tr
    assert tr("en", "build_sub_replacing_part", name="x") == "Replacing x..."
    assert tr("de", "build_sub_done") == tr("ru", "build_sub_done")


def test_no_inline_language_ternaries():
    """Текст для человека - в TRANSLATIONS, а не строкой `... if language == 'en' else ...`:
    иначе новый язык пришлось бы дописывать в двух местах"""
    import re
    from pathlib import Path
    src = Path(__file__).resolve().parent.parent / "src"
    cond = r"""if\s+((\w+\.)?(lang|language)\s*==\s*['"]en['"]|en)\s+else"""
    # Строка до условия на той же строке кода или условие отдельной строкой
    # между двумя строками текста (многострочный тернарий)
    head = r"""if\s+((\w+\.)?(lang|language)\s*==\s*['"]en['"]|en)\s*$"""
    raw = re.compile(r"""['"]\)?\s*""" + cond + r"""\b|^\s*""" + cond + r"""\s*$"""
                     + r"""|['"]\s*""" + head)
    assert raw.search('''emit(-1, f"Converting {x}..." if language == "en"''')
    assert raw.search('''x = "Done" if language == "en" else "Готово"''')
    assert raw.search('''        if r.language == 'en' else''')
    assert raw.search('''a: "Extracting..." if en else "Извлечение..."''')
    assert not raw.search('''english = ({} if lang == 'en' else''')
    found = [f"{p.relative_to(src)}:{n}" for p in src.rglob("*.py")
             for n, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1)
             if raw.search(line)]
    assert not found, "строки интерфейса - через tr():\n" + "\n".join(found)
