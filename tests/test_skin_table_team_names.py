"""Таблица скинов и командные имена: одно правило на весь код"""

from src.shared.skin_rows import SkinTable
from src.shared.team_names import blue_name, is_blue, is_blue_of, team_form


def test_team_form_knows_every_spelling():
    assert team_form('c_scattergun_blue') == ('c_scattergun', True)
    assert team_form('C_Scattergun_BLU') == ('c_scattergun', True)
    assert team_form('c_ambassador_opt_blue_xmas') == ('c_ambassador_opt_xmas', True)
    assert team_form('festive_lights_red') == ('festive_lights', False)
    assert team_form('c_sd_cleaver_bloody') == ('c_sd_cleaver_bloody', False)


def test_pairs_and_new_names():
    assert is_blue_of('festive_lights_red', 'festive_lights_blue')
    assert is_blue_of('c_boxing_gloves_flames', 'c_boxing_gloves_flames_blue')
    assert not is_blue_of('c_x_blue', 'c_x_blue')
    assert not is_blue_of('c_x', 'c_y_blue')
    assert is_blue('hat_blu') and not is_blue('hat')
    assert blue_name('engineer_red') == 'engineer_blue'
    assert blue_name('c_x') == 'c_x_blue'


GRU = SkinTable([['c_boxing_gloves', 'lens'], ['c_boxing_gloves_blue', 'lens'],
                 ['c_boxing_gloves_flames', 'lens'], ['c_boxing_gloves_flames_blue', 'lens'],
                 ['c_boxing_gloves_gold', 'lens'], ['c_boxing_gloves_gold', 'lens']])


def test_table_rows_and_columns():
    assert GRU.col_of('LENS') == 1 and GRU.col_of('nope') == -1
    assert GRU.changes(2, 'c_boxing_gloves') and not GRU.changes(2, 'lens')
    assert not GRU.changes(0, 'c_boxing_gloves')
    assert GRU.cells('c_boxing_gloves_flames_blue') == [(3, 0)]
    assert GRU.is_team_row(1) and not GRU.is_team_row(2)


def test_table_style_pairs():
    assert GRU.blu_row(2) == 3 and GRU.red_row(3) == 2 and GRU.red_row(2) == 2
    assert GRU.blu_row(4) == 0
    assert GRU.team_differs(2, 0) and not GRU.team_differs(2, 1)
    assert GRU.gold_row() == 4
    assert GRU.style_rows(4) == [4, 5]
    assert not SkinTable() and SkinTable().style_rows(0) == []


def test_one_name_rule_for_preview_and_model():
    from src.shared.skin_rows import find_name
    assert find_name(["c_bat", "lens"], "LENS") == 1
    # SMD пишет имя с префиксом пути, $texturegroup - без него
    assert find_name(["c_bat"], "models/weapons/c_bat") == 0
    assert find_name(["c_bat"], "nope") == -1
    assert SkinTable([["c_bat"]]).col_of("models/weapons/c_bat") == 0


def test_style_blue_row_by_any_column():
    """Синяя пара стиля - по всем столбцам, не только по первому"""
    from src.shared.skin_rows import blu_twin
    rows = [["body", "flames"], ["body", "flames_blue"],
            ["body", "flames_hot"], ["body", "flames_hot_blue"]]
    assert blu_twin(rows, 2) == 3


def test_cells_are_only_replacements():
    t = SkinTable([["c_x", "c_x_bloody"], ["c_x_bloody", "c_x_bloody"], ["c_x", "c_x_bloody"]])
    assert t.cells("c_x_bloody") == [(1, 0)]
    assert t.cells("c_x") == []


def test_team_reference_is_stable():
    from src.services.qc_skin_parser import team_reference
    rows = [["engineer_red", "x"], ["engineer_blue", "x"]]
    assert team_reference(rows) == (0, "engineer_blue")


def test_tail_match_only_on_path_boundary():
    from src.shared.skin_rows import find_name
    assert find_name(["c_rocketlauncher_lens", "c_rocketlauncher"], "lens") == -1
    assert find_name(["c_hat"], "models/x/c_hat") == 0


def test_part_of_a_prefixed_base_keeps_its_column():
    from src.services.part_materials import add_part_columns
    rows, variants = add_part_columns([["c_hat"], ["c_hat_blue"]], [("p1", "models/x/c_hat")])
    assert rows[0][-1] == "p1"
    assert rows[1][-1] != "p1" and variants[rows[1][-1]] == "c_hat_blue"
