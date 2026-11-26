"""Карточка австралия: что на ней и что уходит в сборку

Австралий в игре - стиль со скинами 2 (RED) и 3 (BLU). У большинства
оружия золото у команд одно (клеймор), у части - своё синее (Посол,
`c_ambassador_blue_gold`). Пока своей картинки нет, карточка берёт её из
выбранного источника:

  • 'game' - игровое золото команды;
  • 'base' - как обычная карточка той же команды (у своей геометрии это
    умолчание: игровое золото легло бы мимо её развёртки);
  • 'red'  - у синего золота как красное

Своя картинка главнее выбора, а выбор её снимает - как у синей карточки
(PreviewTextureState.blu_choices). Хранение своих картинок - общее
(`textures` по командам), командность золота - `is_team_material`
"""

from __future__ import annotations

from typing import Dict, List, Optional

from src.shared.constants import Team
from src.shared.file_utils import existing_file


def blue_name(t) -> Optional[str]:
    """Синее золото: своё у оружия (Посол) или дописанное «сделать
    командным» - тогда `<золото>_blue` (qc_skin_parser.force_team_rows)"""
    gold = t.australium_mat_name
    if t.australium_blu_mat:
        return t.australium_blu_mat
    return f'{gold}_blue' if gold and t.force_team else None


def options(t, team: Optional[str] = None) -> List[str]:
    """Откуда может брать картинку карточка австралия у команды"""
    team = team or t.active_team
    if team == Team.BLU and blue_name(t):
        return ['game', 'red', 'base']
    return ['game', 'base']


def _side(t, team: str) -> str:
    """Чья запись выбора: у общего золота (одно на обе команды, как у
    ракетомёта) она одна - красная. Иначе выбор на синих не доходил бы до
    сборки: общий материал собирается один раз"""
    gold = t.australium_mat_name
    return team if gold and t.is_team_material(gold) else Team.RED


def _own(t, team: str) -> Optional[str]:
    """Своя картинка золота; `australium_user_tex` - из работ до карточки"""
    gold = t.australium_mat_name
    return (t.own_at(gold, 0, team) if gold else None) or existing_file(t.australium_user_tex)


def choice(t, team: Optional[str] = None) -> str:
    """'own' - своя картинка, иначе выбранный (или умолчательный) источник"""
    team = _side(t, team or t.active_team)
    if _own(t, team):
        return 'own'
    chosen = t.variant_source.get(team, '')
    if chosen in options(t, team):
        return chosen
    return 'base' if t.custom_geometry() else 'game'


def set_choice(t, value: str) -> bool:
    """Источник у показанной команды. Своя картинка снимается: выбор и есть
    отказ от неё"""
    team, gold = t.active_team, t.australium_mat_name
    if not gold or value not in options(t, team):
        return False
    side = _side(t, team)
    for each in ((side,) if t.is_team_material(gold) else (Team.RED, Team.BLU)):
        t.textures.get(each, {}).pop(gold, None)
    t.australium_user_tex = None
    t.variant_source[side] = value
    return True


def game(t, team: Optional[str] = None) -> Optional[str]:
    """Игровое золото команды"""
    team = team or t.active_team
    blu = existing_file(t.australium_blu_frame) if team == Team.BLU else None
    return blu or existing_file(t.australium_frame)


def shown(t, team: Optional[str] = None) -> Optional[str]:
    """Что показывает карточка австралия у команды"""
    team = team or t.active_team
    side = _side(t, team)
    own = _own(t, side)
    if own:
        return own
    source = choice(t, team)
    if source == 'base':
        # У общего золота - обычная красных: в игре один материал на обе
        return t.shown_at(t.stable_main() or t.storage_main_key(), 0, side)
    if source == 'red':
        return shown(t, Team.RED)
    return game(t, team)


def build_images(t) -> Dict[str, str]:
    """{материал золота: картинка} для сборки - то, что видно на карточке у
    каждой команды, кроме игрового: его сборка пишет оригиналом сама"""
    out: Dict[str, str] = {}
    # Дописанного синего золота в игре нет: его картинка нужна и игровой,
    # иначе синий австралий вышел бы фиолетовым
    made_up = not t.australium_blu_mat and bool(blue_name(t))
    for name, team in ((t.australium_mat_name, Team.RED), (blue_name(t), Team.BLU)):
        must = made_up and team == Team.BLU
        if not name or (choice(t, team) == 'game' and not must):
            continue
        path = existing_file(shown(t, team))
        if path and (must or path != game(t, team)):
            out[name] = path
    return out


# Мод из VPK: золото - свои VTF мода (mod_variant)

def side_of(t, mat: str) -> Optional[str]:
    """Команда, чьё это золото (RED - карточка австралия, BLU - её синяя
    сторона), иначе None. Своя картинка лежит под карточкой австралия"""
    low = (mat or '').lower()
    if t.is_variant_material(mat):
        return Team.RED
    blue = t.australium_blu_mat
    return Team.BLU if blue and low == blue.lower() else None


def mod_blue_upload(t) -> Dict[str, str]:
    """{синее золото мода: своя картинка} - у мода это свой VTF"""
    gold, blue = t.australium_mat_name, t.australium_blu_mat
    own = existing_file(t.textures.get(Team.BLU, {}).get(gold)) if gold and blue else None
    return {blue: own} if own and own != t.textures.get(Team.RED, {}).get(gold) else {}


def on_mesh(t, mat: str, card: Optional[str]) -> bool:
    """Рисует ли меш мода австралий: меши, чьи материалы заменяет его строка,
    иначе меши главной карточки - как у игрового предмета"""
    if not t.variant_display_texture():
        return False
    if t.variant_meshes:
        return (mat or '').lower() in t.variant_meshes
    return (card or mat or '').lower() == (t.stable_main() or '').lower()
