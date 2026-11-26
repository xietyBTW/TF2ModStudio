"""
«Сделать командным» и его отмена

Включение - флаг в PreviewTextureState: синюю строку синтезирует сборка, а
выбор синей («Игровая / Как красная / своя») тот же, что у игровой командной
карточки (_blue_card). Отмена живёт здесь: она чистит то, что существовало
только из-за командности
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from src.shared.constants import Team

if TYPE_CHECKING:
    from src.domain.preview.texture_state import PreviewTextureState


def apply(t: "PreviewTextureState") -> None:
    """
    Предмет становится командным: показываются RED/BLU, активна RED

    Картинка, положенная до включения, легла копией в обе команды (карточка
    была общей). Копия в синей - не своя синяя: оставленная, она показывала
    красную при выборе «Игровая». Своя синяя (отличная от красной) остаётся
    """
    red = t.textures.get(Team.RED, {})
    blu = t.textures.get(Team.BLU, {})
    for mat in list(blu):
        if (not t.is_team_material(mat) and not t.is_variant_material(mat)
                and blu[mat] == red.get(mat)):
            blu.pop(mat, None)
    t.force_team = True
    t.active_team = Team.RED


def remove(t: "PreviewTextureState") -> None:
    """
    Предмет снова один на обе команды

    Синие картинки и «Как красная» базы были только у командности.
    Оставленные, они вылезли бы на красной: у некомандной карточки один слот
    на обе команды (own_at берёт картинку другой команды). Выбор у стилей
    (ключ `карточка@строка`) - игровые командные пары, их не трогаем
    """
    blu = t.textures.get(Team.BLU, {})
    for mat in list(blu):
        if not t.is_team_material(mat) and not t.is_variant_material(mat):
            blu.pop(mat, None)
    t.blu_like_red = {key for key in t.blu_like_red if '@' in key}
    t.force_team = False
    t.active_team = Team.RED
