"""
Вид редактируемого предмета - один ответ вместо россыпи проверок по строке

Режим (`mode`) в приложении - строка: 'hat', 'scout_c_scattergun',
'engineer_arms', 'spy_body', 'spy_masks'… По ней код 107 раз в 12 файлах
спрашивал одно и то же разными способами:

    if mode == "hat": ...
    if mode in HAND_MODE_KEYS: ...
    if mode in PLAYER_BODY_MODE_KEYS: ...
    if mode == SPY_MASK_MODE_KEY: ...

Каждый новый вид предмета (скайбокс, частицы, наборы шапок) означал найти и
поправить все такие места - и ничто не мешало одно пропустить. Здесь вид
определяется ОДИН раз, а вопросы к нему задаются по имени:

    kind = kind_of(mode)
    if kind.is_hat: ...
    if kind.multi_material: ...

Вопросы - про ПОВЕДЕНИЕ (`asks_game_paints`, `styles_are_models`), а не
про имя вида: новый вид предмета - одна строка в таблице `_KINDS`, и каждое
место кода сразу знает, как с ним обращаться. Прямые проверки режима вне
этого модуля запрещает tests/test_item_kind_ratchet.py

Модуль знает только про КЛАССИФИКАЦИЮ. Данные конкретного предмета (пути
моделей, текстуры, классы) остаются в своих таблицах - weapons, player_hands,
player_characters и прочих, дублировать их здесь нельзя
"""

from dataclasses import dataclass
from typing import Dict

#: Шапка/косметика: модель приходит из списка шапок, а не из таблицы оружия
HAT = "hat"
#: Руки (вьюмодель): своя таблица материалов, несколько текстур на модель
HANDS = "hands"
#: Тело персонажа: много материалов, командные пары имён
CHARACTER = "character"
#: Маски маскировки шпиона: отдельная панель и свой набор текстур
SPY_MASK = "spy_mask"
#: Оружие и всё остальное, что описано таблицей WEAPON_MDL_PATHS
WEAPON = "weapon"
#: Мод из VPK пользователя: предмета в каталоге нет, его опознаёт файл
MOD = "custom"


@dataclass(frozen=True)
class ItemKind:
    """Что это за предмет и как с ним обращаться"""

    key: str
    #: Ключ модели - сразу путь MDL (шапка, тело, маска), а не имя оружия:
    #: искать его по таблице оружия и вешать на носитель нечего
    model_by_path: bool = False
    #: У модели заведомо несколько материалов - текстуры собираются картой.
    #: Руки и тела: один общий кадр натянул бы лицо на рукав. У шапок и
    #: оружия это решается по факту
    multi_material: bool = False
    #: SMD модели уже в мировой ориентации (не требует разворота)
    model_is_z_up: bool = True
    #: Модель собрана против скелета игрока и в игре сливается с ним
    #: (bonemerge): превью ставит её в позу игрока (см. cosmetic_pose)
    worn_on_player: bool = False
    #: Перед сборкой спрашиваем, оставлять ли краски игры (VMT-прокси)
    asks_game_paints: bool = False
    #: Стиль - отдельная модель со своими правками (снимки стилей шапки),
    #: а не строка таблицы скинов: стиль открывается с нулевой строки, а
    #: неактивные изменённые стили собираются своими моделями
    styles_are_models: bool = False
    #: Своя модель на каждый класс: сборка пишет выбранные классы
    class_models: bool = False
    #: Геометрию можно заменить своей моделью
    replaceable_model: bool = True
    #: «Сделать командным»: синтез RED/BLU в $texturegroup своей модели
    can_force_team: bool = False
    #: Предмет держат в руках: вид от первого лица и War Paint игры. Мод из
    #: VPK тоже - его оружие знает превью (custom_vpk_weapon)
    held: bool = False

    @property
    def is_hat(self) -> bool:
        return self.key == HAT

    @property
    def is_hands(self) -> bool:
        return self.key == HANDS

    @property
    def is_character(self) -> bool:
        return self.key == CHARACTER

    @property
    def is_spy_mask(self) -> bool:
        return self.key == SPY_MASK

    @property
    def is_weapon(self) -> bool:
        return self.key == WEAPON

    @property
    def is_mod(self) -> bool:
        return self.key == MOD


_KINDS = (
    ItemKind(HAT, model_by_path=True, worn_on_player=True, asks_game_paints=True,
             styles_are_models=True, class_models=True),
    ItemKind(HANDS, multi_material=True, replaceable_model=False),
    ItemKind(CHARACTER, model_by_path=True, multi_material=True, model_is_z_up=False),
    ItemKind(SPY_MASK, model_by_path=True),
    ItemKind(WEAPON, can_force_team=True, held=True),
    ItemKind(MOD, held=True),
)
_BY_KEY: Dict[str, ItemKind] = {k.key: k for k in _KINDS}


def kind_of(mode: str) -> ItemKind:
    """Вид предмета по режиму приложения. Неизвестный режим - оружие"""
    from src.data.player_characters import PLAYER_BODY_MODE_KEYS, SPY_MASK_MODE_KEY
    from src.data.player_hands import HAND_MODE_KEYS

    key = (mode or "").strip()
    if key in (HAT, MOD):
        return _BY_KEY[key]
    if key == SPY_MASK_MODE_KEY:
        return _BY_KEY[SPY_MASK]
    if key in HAND_MODE_KEYS:
        return _BY_KEY[HANDS]
    if key in PLAYER_BODY_MODE_KEYS:
        return _BY_KEY[CHARACTER]
    return _BY_KEY[WEAPON]
