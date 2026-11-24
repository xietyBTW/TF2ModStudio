"""Строки скина, которые игра включает: по имени, коду или items_game"""

from src.data import item_skin_styles as iss
from src.services import qc_skin_parser as q


def test_katana_blood_is_a_named_style():
    """Полудзатоити: строки 2/3 игра включает после обезглавливания"""
    layout = q.classify_rows([['c_shogun_katana', 'c_shogun_katana_blood']] * 2
                             + [['c_shogun_katana_blood', 'c_shogun_katana_blood']] * 2)
    assert q.selector_spec(layout).styles == [('Bloody', 2)]


def test_named_item_style_gives_its_skin():
    """Чёрная роза: `styles { 1 { skin_red 2, name … } }`"""
    visuals = '''{
        "styles"
        {
            "0" { "skin_red" "0" "skin_blu" "1" "name" "#TF_BlackRose_Style_TeamColors" }
            "1" { "skin_red" "2" "skin_blu" "3" "name" "#TF_BlackRose_Style_Black" }
            "2" { "skin_red" "8" "skin_blu" "9" }
        }
    }'''
    assert iss._style_skins(visuals) == [(2, 'TF_BlackRose_Style_Black')]


def test_skin_inside_a_style_is_not_the_items_own():
    """`skin` стиля не должен сойти за `visuals { skin }` самого предмета"""
    visuals = '{ "sound" "x" "styles" { "1" { "skin" "4" } } }'
    assert iss._SKIN_RE.search(iss._own_skin_block(visuals)) is None
    assert iss._SKIN_RE.search(iss._own_skin_block('{ "skin" "2" }')).group(1) == '2'
