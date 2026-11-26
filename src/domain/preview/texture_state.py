"""
Модель состояния текстур 2D/3D-превью (чистый Python, юнит-тестируется)

ЕДИНЫЙ источник правды о текстурах и все правила маршрутизации в одном месте
(нейтральная текстура -> обе команды, вариантный стиль -> skin_overrides,
приоритеты разрешения), чтобы 2D и 3D не расходились:

  • set_texture()          - куда пишется загруженная пользователем текстура;
  • resolve_card()/resolve_base() - что показывает карточка/2D при текущей
    команде/стиле (пользовательская -> другая команда для нейтральных ->
    VPK-оригинал -> командный кадр);
  • uploaded_for_mat()/uploaded_slot_paths()/blu_uploaded_paths() - что уходит
    в сборку;
  • variant_display_texture() - что показывает активный вариант (Australium)

Сеанс (PreviewSession) держит экземпляр и делегирует сюда и хранение, и
разрешение
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Set, Tuple

from src.shared.file_utils import existing_file
from src.domain.preview import variant_card
from src.shared.constants import EXTRA_TEX_USE_GAME_ORIGINAL, EXTRA_TEX_USE_MAIN, Team
from src.shared.skin_rows import SkinTable
from src.shared.team_names import BLUE_SUFFIXES, team_form

# Sentinel-ключ главной текстуры, когда у модели нет именованных материалов
# (одноматериальный случай). НЕ имя материала и НЕ должен попадать в сборку
SINGLE_TEX_KEY = '__single__'

#: Приставка карточек гирлянды поверх оружия (праздничная версия,
#: фестивайзер): `deco:<вид>/<материал>`. Гирлянда - отдельная модель со
#: своими материалами: стилей у неё нет, в сборку оружия она не идёт (её
#: собирает свой шаг, см. decor_build), а игровой оригинал лежит в
#: `decor_stock`, а не в картах модели оружия - те пересобираются с каждой
#: загрузкой модели
DECOR_PREFIX = 'deco:'


def blue_image(own_blue: Optional[str], red: Optional[str], like_red: bool) -> Optional[str]:
    """Синяя картинка командной карточки: своя, иначе красная при «Как
    красная», иначе None - игровая синяя. Одно правило для слотов превью
    (PreviewTextureState.inherited) и неактивных стилей шапки при сборке"""
    return own_blue or (red if like_red else None)


def is_decor(mat: Optional[str]) -> bool:
    """Карточка гирлянды, а не материал самого предмета"""
    return bool(mat) and str(mat).startswith(DECOR_PREFIX)


def team_priority(active_team: str) -> List[str]:
    """Порядок проверки команд: активная первой (сборка может начаться с BLU)"""
    if active_team == Team.BLU:
        return [Team.BLU, Team.RED]
    return [Team.RED, Team.BLU]


_existing = existing_file


def _lookup_ci(store: Dict[str, str], key: str) -> Optional[str]:
    """Значение по ключу, с фолбэком на совпадение без учёта регистра

    Нужно моду из VPK: карточки там названы по VTF, а меши модели - по
    материалам, и совпадают они через раз только регистром
    """
    if key in store:
        return store[key]
    low = key.lower()
    for name, value in store.items():
        if name.lower() == low:
            return value
    return None


@dataclass
class PreviewTextureState:
    """Состояние текстур превью: пользовательские загрузки + данные модели"""

    # Пользовательские текстуры
    #: {team: {mat_name: path}} - загруженные пользователем (skin 0)
    textures: Dict[str, Dict[str, str]] = field(
        default_factory=lambda: {Team.RED: {}, Team.BLU: {}})
    #: {skin_idx: {mat_name: path}} - переопределения вариантных стилей (skin > 0)
    skin_overrides: Dict[int, Dict[str, str]] = field(default_factory=dict)
    #: {skin_idx: {базовый материал: png}} - ОРИГИНАЛЫ текстур стиля из игры или
    #: из мода. Не правки: в user_edits и в сборку не идут, показ их лишь
    #: подставляет, пока человек не положил свою (см. resolve_card)
    style_game_tex: Dict[int, Dict[str, str]] = field(default_factory=dict)

    # Активные селекторы
    active_team: str = Team.RED
    active_skin: int = 0
    #: dict из SkinDetectWorker (num_skins, roles, …) или None - стили не определены
    skin_info: Optional[dict] = None

    @property
    def style_row(self) -> int:
        """Строка таблицы скинов, которую сейчас показывают и правят в стиле
        (0 - стиль не открыт)"""
        return self.row_for(self.active_team)

    def row_for(self, team: str) -> int:
        """Строка открытого стиля для команды. У стиля с синей парой (огонь
        Горящих рукавиц ускорения) у BLU это его синяя строка"""
        if not (self.skin_info and self.active_skin):
            return 0
        blue = (self.table.blu_row(self.active_skin)
                if team == Team.BLU and self.pair_styles() else 0)
        return blue or self.active_skin

    #: Есть ли у стилей синие строки игровой таблицы. Своя модель собирает
    #: стили сама, пар по именам у неё нет - выключает PreviewSession
    pair_styles: Callable[[], bool] = field(default=lambda: True, repr=False, compare=False)
    #: «Сделать командным» (+ Команда): оружие БЕЗ нативной команды, которому
    #: пользователь синтезирует RED/BLU. У таких материалов нет blu_name_map/
    #: blu_frames, поэтому is_neutral() их считает нейтральными - но при force_team
    #: загрузка НЕ должна дублироваться в обе команды (иначе BLU затирает RED и
    #: 2D/3D показывают одинаковое). См. set_texture()
    force_team: bool = False

    # Данные модели (заполняются воркерами превью)
    #: Имена материалов геометрии; [0] - главный. ВНИМАНИЕ: в режиме «Прочее»
    #: временно подменяется служебными - стабильное имя главного в main_material
    material_names: List[str] = field(default_factory=list)
    #: Стабильное имя главного материала (не зависит от «Прочее»)
    main_material: Optional[str] = None
    #: {red_mat: blu_display_name} - командные пары материалов (персонажи/руки)
    blu_name_map: Dict[str, str] = field(default_factory=dict)
    #: {синий материал в нижнем регистре: его RED-пара} - в игре синий
    #: выглядит в точности как красный. Карточки у такого нет, поэтому
    #: сборка отдаёт ему правку красного, иначе синие видели бы сток
    blu_twins: Dict[str, str] = field(default_factory=dict)
    #: Командные карточки, у которых синяя берёт картинку красной («Как
    #: красная»). Без отметки и без своей синей - игровая синяя
    blu_like_red: Set[str] = field(default_factory=set)
    #: Игровые оригиналы из VPK: {red_mat: png} по командам (ключи - RED-имена)
    vpk_red_tex_map: Dict[str, str] = field(default_factory=dict)
    vpk_blu_tex_map: Dict[str, str] = field(default_factory=dict)
    #: Мод из VPK: {материал модели в нижнем регистре: карточка}. Карточки
    #: мода названы по его VTF, а меши - по материалам; связь - VMT материала
    #: (vpk_mod_models.mesh_links)
    mod_mesh_cards: Dict[str, str] = field(default_factory=dict)
    #: Командная текстура одним кадром (кадры анимации): пути PNG
    red_frames: List[str] = field(default_factory=list)
    blu_frames: List[str] = field(default_factory=list)

    # Вариант Australium/Gold
    australium_frame: Optional[str] = None      # игровой gold-кадр (PNG)
    australium_user_tex: Optional[str] = None   # своя текстура варианта
    australium_mat_name: Optional[str] = None   # имя gold-материала (для сборки)
    australium_active: bool = False             # активен ли вариант в превью
    #: Синее золото: у части оружия (Посол) в скине 3 свой материал
    #: `c_ambassador_blue_gold`. Пусто - золото у команд одно (клеймор)
    australium_blu_frame: Optional[str] = None
    australium_blu_mat: Optional[str] = None
    #: Меши мода, чьи материалы строка австралия заменяет (mod_variant)
    variant_meshes: Set[str] = field(default_factory=set)
    #: Откуда картинка карточки австралия, пока своей нет: {команда: 'game' |
    #: 'base' (как обычная) | 'red' (у синего золота - как красное)}. Нет
    #: записи - по умолчанию (variant_choice)
    variant_source: Dict[str, str] = field(default_factory=dict)
    #: Своя геометрия в кадре: игровое золото легло бы мимо её развёртки, и
    #: австралий по умолчанию берёт обычную. Подключает PreviewSession
    custom_geometry: Callable[[], bool] = field(default=lambda: False, repr=False, compare=False)

    # Режим «Скайбокс»
    # Пользовательские грани/панорама живут в textures (ключи - грани из
    # SKY_FACES и SKY_PANO_KEY, нейтральные -> обе команды), здесь - данные,
    # которые панель получает от воркеров.
    #: Стоковые грани выбранного неба из VPK игры: {face: png}
    skybox_stock_faces: Dict[str, str] = field(default_factory=dict)
    #: Грани, нарезанные из загруженной панорамы: {face: png}
    skybox_split_faces: Dict[str, str] = field(default_factory=dict)

    # Гирлянда поверх оружия
    #: Игровые кадры гирлянды: {team: {карточка deco:…: png}}. Кладёт сеанс,
    #: когда гирлянда разобрана, свои правки гирлянды живут в `textures`
    decor_stock: Dict[str, Dict[str, str]] = field(default_factory=dict)

    # Части, ставшие своими материалами
    #: {материал части: карточка исходного}. Материал части - отдельная
    #: карточка: своя картинка по командам, без неё - игровая текстура
    #: исходного (см. src/services/part_materials.py). Ведёт PreviewSession
    part_cards: Dict[str, str] = field(default_factory=dict)

    # Ключи / классификация материалов

    def storage_main_key(self) -> str:
        """Ключ ХРАНЕНИЯ главной текстуры (как исторически пишет load_image)"""
        return self.material_names[0] if self.material_names else SINGLE_TEX_KEY

    def stable_main(self) -> Optional[str]:
        """Стабильное имя главного материала независимо от режима «Прочее»"""
        if self.main_material:
            return self.main_material
        return self.material_names[0] if self.material_names else None

    def is_team_material(self, mat: str) -> bool:
        """True, если материал КОМАНДНЫЙ (есть свой синий вариант)

        С per-material маппингом - синее имя отличается от красного
        (medic_hands_red->medic_hands_blue). Без маппинга - главный материал
        командный, если BLU пришёл одним кадром (blu_frames): синий вариант
        существует, просто не по-материально. Это ЕДИНОЕ правило командности -
        им пользуются и хранение (is_neutral), и разрешение (resolve_base);
        расхождение этих двух путей давало «на BLU показывается RED» у
        мульти-материальных шапок с одним BLU-кадром
        """
        if is_decor(mat):
            return self._decor_team(mat)
        # Золото командное, только если у синих своё (variant_card.blue_name)
        if self.is_variant_material(mat):
            from src.domain.preview import variant_card
            return bool(variant_card.blue_name(self))
        # Материал части командный, если командный его исходный: в сборке у
        # него строки скина исходного (`_blue` на месте синего)
        base = self.part_cards.get(mat)
        if base and base != mat:
            return self.is_team_material(base)
        # Карта ключуется настоящими именами, а карточка одноматериальной
        # модели живёт под служебным ключом: по карте она всегда выходила
        # общей, и на BLU шарф Stockbroker's Scarf оставался красным
        if self.blu_name_map and mat != SINGLE_TEX_KEY:
            bn = self.blu_name_map.get(mat, mat)
            return bn.lower() != mat.lower()
        if self.blu_frames:
            main_key = self.main_material or self.storage_main_key()
            return mat in (main_key, SINGLE_TEX_KEY)
        return False

    def _decor_team(self, mat: str) -> bool:
        """Командна ли карточка гирлянды: у синих свои огоньки (кадры разные)

        Карта имён модели оружия (`blu_name_map`) гирлянды не знает, и
        судить по ней значило бы считать огоньки фестивайзера общими - тогда
        правка на красных легла бы и на синие
        """
        red = self.decor_stock.get(Team.RED, {}).get(mat)
        blu = self.decor_stock.get(Team.BLU, {}).get(mat)
        return bool(red and blu and red != blu)

    def is_neutral(self, mat: str) -> bool:
        """True, если текстура не относится к конкретной команде (RED/BLU)

        Нейтральные (sniper_lens, c_arrow, eyeball_r …) одинаковы для обеих
        команд - хранятся в обоих словарях, чтобы карточка не пропадала при
        переключении команды

        Материал, который САМ есть в маппинге, судим по его паре: стал собой -
        значит общий. Это не крючкотворство: у многоматериальных шапок
        (hwn2022_alcoholic_automaton) BLU-имя одной колонки одновременно
        является обычным материалом другой - линза там всегда синяя и по
        команде не меняется, а по правилу «имя есть среди значений» карточка
        считалась бы командной и пропадала при переключении

        Имя, которое встречается ТОЛЬКО как значение (medic_hands_blue у рук),
        нейтральным по-прежнему не считается: это чисто синий материал
        """
        if is_decor(mat):
            return not self._decor_team(mat)
        if mat in self.part_cards or self.is_variant_material(mat):
            return not self.is_team_material(mat)
        if self.blu_name_map and mat != SINGLE_TEX_KEY:
            blu = self.blu_name_map.get(mat)
            if blu is not None:
                return blu.lower() == mat.lower()
            low = mat.lower()
            return not any(str(v).lower() == low for v in self.blu_name_map.values())
        return not self.is_team_material(mat)

    # Слот карточки: строка таблицы скинов и команда
    #
    # Всё, что карточка показывает, хранит и отдаёт сборке, считается здесь
    # от слота (row, team), а не от активных селекторов в каждом месте
    # отдельно. Строка 0 - база (правки по командам в `textures`), иначе
    # строка стиля (правки в `skin_overrides[row]`). Синяя строка стиля - его
    # отдельный слот, как синяя команда у базы, и «Как красная» у неё та же

    @property
    def table(self) -> SkinTable:
        """Таблица скинов модели (пустая, пока стили не определены)"""
        rows = (self.skin_info or {}).get('rows') or []
        cached = self.__dict__.get('_table')
        if cached is None or cached[0] is not rows:
            cached = self.__dict__['_table'] = (rows, SkinTable(rows))
        return cached[1]

    def red_row(self, row: int) -> int:
        """Красная строка слота: у синей строки стиля - его красная"""
        return self.table.red_row(row)

    def col_of(self, card: str) -> int:
        """Столбец таблицы скинов карточки: у части - её исходного, у
        одноматериальной модели - первый"""
        base = self.part_cards.get(card, card)
        return 0 if base == SINGLE_TEX_KEY else self.table.col_of(base)

    def _paired(self, mat: str, red: int) -> bool:
        """Своя ли у карточки синяя в стиле `red` (0 - база): у базы это
        командный материал, у стиля - отличающийся столбец его синей строки"""
        if not red:
            return self.is_team_material(mat)
        return self.pair_styles() and self.table.team_differs(red, self.col_of(mat))

    def _blue_card(self, mat: str, red: int) -> bool:
        """
        Есть ли у карточки своя синяя сторона с выбором «Игровая / Как
        красная / своя»

        Игровая командная - своя пара. Под «сделать командным» - каждая
        обычная карточка базы: синюю строку синтезирует сборка. Правило одно,
        иначе сделанная командной синяя молча повторяла красную, а выбора на
        карточке не было. Австралий и гирлянда командой не делятся
        """
        if is_decor(mat):
            return False
        if self._paired(mat, red):
            return True
        return (self.force_team and not red and not self.is_team_material(mat)
                and not self.is_variant_material(mat))

    @staticmethod
    def _like_key(mat: str, red: int) -> str:
        """Ключ «Как красная» в `blu_like_red`: у базы - сама карточка"""
        return f'{mat}@{red}' if red else mat

    def own_at(self, mat: str, row: int, team: str) -> Optional[str]:
        """Своя картинка человека в слоте, без разрешения"""
        if row and not is_decor(mat):
            return _existing(self.skin_overrides.get(row, {}).get(mat))
        own = _existing(self.textures.get(team, {}).get(mat))
        # Общая карточка - один слот на обе команды, лежит копией в каждой
        if not own and not self.force_team and not self.is_team_material(mat):
            other = Team.BLU if team == Team.RED else Team.RED
            own = _existing(self.textures.get(other, {}).get(mat))
        return own

    def underlay(self, mat: str, row: int, team: str) -> Optional[str]:
        """Что слот показывает без своей картинки: взятое у красной
        (inherited), иначе игровой оригинал"""
        inherited = self.inherited(mat, row, team)
        if inherited:
            return inherited
        if row and not is_decor(mat):
            return self._style_game(mat, row)
        # Материал части без своей картинки - игровая текстура исходного:
        # картинка на исходном его не касается, это отдельный материал
        return self.game_base(mat, team)

    def inherited(self, mat: str, row: int, team: str) -> Optional[str]:
        """Картинка красной, которую синий слот берёт вместо игровой: «Как
        красная» или своя красная под «сделать командным». Сборке это та же
        своя картинка слота"""
        if team != Team.BLU or is_decor(mat):
            return None
        red = self.red_row(row)
        if self._blue_card(mat, red):
            like = self._like_key(mat, red) in self.blu_like_red
            return blue_image(None, like and self.shown_at(mat, red, Team.RED), like)
        return None

    def shown_at(self, mat: str, row: int, team: str) -> Optional[str]:
        """Что показывает карточка в слоте"""
        return self.own_at(mat, row, team) or self.underlay(mat, row, team)

    def _style_game(self, mat: str, row: int) -> Optional[str]:
        """Оригинал стиля, у материала части - оригинал стиля исходного
        (строка стиля ведёт часть в игровой VMT его материала)"""
        game = self.style_game_tex.get(row, {})
        return _existing(game.get(mat)) or _existing(game.get(self.part_cards.get(mat, mat)))

    # Запись

    def set_texture(self, mat: str, path: Optional[str]) -> None:
        """Сохраняет (или сбрасывает, path=None) пользовательскую текстуру

        Маршрутизация:
          • активен вариантный стиль (skin > 0) -> skin_overrides его строки;
          • нейтральная -> обе команды;
          • командная -> только активная команда
        """
        # Своя синяя заменяет выбор «Как красная»: снимешь её - вернётся игровая
        if path and self.active_team == Team.BLU:
            self.blu_like_red.discard(self._like_key(mat, self.row_for(Team.RED)))
        # Стилей у гирлянды нет: правка стиля оружия её не касается
        if self.style_row and not is_decor(mat):
            slot = self.skin_overrides.setdefault(self.style_row, {})
            if path:
                slot[mat] = path
            else:
                slot.pop(mat, None)
            return

        # Нейтральная текстура пишется в обе команды, чтобы карточка не пропадала
        # при переключении команды. ИСКЛЮЧЕНИЕ - force_team: там пользователь
        # намеренно задаёт РАЗНЫЕ текстуры RED/BLU, поэтому дублирование запрещено
        # (иначе загрузка на BLU затирает RED). Дефолт «BLU как RED» до задания
        # своей синей обеспечивает симметричный fallback в resolve_base().
        # Австралий командой не делится и под force_team: сборка красит его
        # одной текстурой для обеих команд (игра так и показывает)
        teams = [self.active_team]
        if self.is_neutral(mat) and (not self.force_team
                                     or self.is_variant_material(mat)):
            teams.append(Team.BLU if self.active_team == Team.RED else Team.RED)
        for team in teams:
            if path:
                self.textures.setdefault(team, {})[mat] = path
            else:
                self.textures.get(team, {}).pop(mat, None)

    # Синяя текстура командной карточки: игровая, как красная или своя

    def blu_choices(self) -> Dict[str, str]:
        """{карточка: 'game' | 'red' | 'own'} у карточек со своей синей в
        открытом слоте, пока показана синяя команда - и у игровой командной,
        и у сделанной командной (_blue_card)"""
        if self.active_team != Team.BLU:
            return {}
        red, blue = self.row_for(Team.RED), self.row_for(Team.BLU)
        out: Dict[str, str] = {}
        for mat in self.material_names:
            if not self._blue_card(mat, red):
                continue
            own = self.own_at(mat, blue, Team.BLU)
            out[mat] = ('own' if own and own != self.own_at(mat, red, Team.RED)
                        else 'red' if self._like_key(mat, red) in self.blu_like_red else 'game')
        return out

    def has_upload(self, mat: str) -> bool:
        """Лежит ли на карточке своя картинка там, где она сейчас показана"""
        return bool(self.own_at(mat, 0 if is_decor(mat) else self.style_row, self.active_team))

    def set_blu_choice(self, mat: str, choice: str) -> None:
        """«Игровая» или «Как красная» у синей карточки открытого слота. Своя
        синяя при этом снимается: выбор и есть отказ от неё"""
        red, blue = self.row_for(Team.RED), self.row_for(Team.BLU)
        if not self._blue_card(mat, red):
            return
        if blue:
            self.skin_overrides.get(blue, {}).pop(mat, None)
        else:
            self.textures.get(Team.BLU, {}).pop(mat, None)
        key = self._like_key(mat, red)
        if choice == 'red':
            self.blu_like_red.add(key)
        else:
            self.blu_like_red.discard(key)

    def build_slot(self, material: str) -> Optional[Tuple[str, int, str]]:
        """Слот карточки, чья картинка уходит в материал сборки (имя из
        $texturegroup): (карточка, строка, команда) или None

        Одна связь для своих картинок стилей, выбора синей и частей: правки
        хранятся под карточкой (базовым материалом), а сборка спрашивает
        материалы строк по их собственным именам (`c_sd_cleaver_bloody`)"""
        low = (material or '').lower()
        twin = self.blu_twins.get(low)
        if twin:
            return self._card_of(twin), 0, Team.RED
        # Сначала ключ по всей карте: синее имя одного столбца бывает своим
        # материалом другого (линза hwn2022_alcoholic_automaton)
        red = next((r for r in self.blu_name_map if r.lower() == low), None)
        if red is not None:
            return self._card_of(red), 0, Team.RED
        red = next((r for r, b in self.blu_name_map.items() if b.lower() == low), None)
        if red is not None:
            return self._card_of(red), 0, Team.BLU
        if material in self.material_names or material in self.part_cards:
            return material, 0, Team.RED
        # Строка стиля раньше базы: у гильотины `c_sd_cleaver_bloody` - и
        # второй меш базы, и материал стиля Bloody, а правка лежит в стиле
        table = self.table
        for row, col in table.cells(material):
            if not table.is_team_row(row):
                red = table.red_row(row)
                return self._card_at(col), row, Team.BLU if red != row else Team.RED
        if table.col_of(material) >= 0:
            return self._card_at(table.col_of(material)), 0, Team.RED
        base, blue = team_form(material)
        # Синее имя, которое синтезирует «сделать командным», - синяя сторона
        # карточки: без слота сборка не знала выбора и спрашивала человека
        if blue and (self.blu_frames or self.force_team):
            card = next((m for m in self.material_names if m.lower() == base), None)
            if card or self.material_names == [SINGLE_TEX_KEY]:
                return self._card_of(card or base), 0, Team.BLU
        return None

    def build_answer(self, material: str) -> Optional[str]:
        """Ответ сборке на текстуру материала без вопроса человеку: своя
        картинка слота или взятая у красной, иначе выбор синей
        (EXTRA_TEX_USE_MAIN / _GAME_ORIGINAL) - или None, тогда спрашивать"""
        slot = self.build_slot(material)
        own = self.uploaded_for_mat(material) or (slot and self.own_at(*slot))
        if own:
            return own
        if not slot:
            return None
        card, row, team = slot
        if team == Team.BLU:
            if row and self.inherited(card, row, team):
                return self.inherited(card, row, team)
            like = self._like_key(card, self.red_row(row)) in self.blu_like_red
            return EXTRA_TEX_USE_MAIN if like and not row else EXTRA_TEX_USE_GAME_ORIGINAL
        # Синий двойник красного без правки: карточки у него нет, а игровой
        # выглядит как красный
        return EXTRA_TEX_USE_GAME_ORIGINAL if (material or '').lower() in self.blu_twins else None

    def _card_at(self, col: int) -> str:
        """Карточка столбца таблицы скинов: у одноматериальной модели она
        одна и лежит под служебным ключом (имени материала превью не знает)"""
        return SINGLE_TEX_KEY if self.material_names == [SINGLE_TEX_KEY] else self.table.rows[0][col]

    def red_of_blu(self, blu_mat: str) -> Optional[str]:
        """Красная карточка синего материала базы сборки, иначе None"""
        slot = self.build_slot(blu_mat)
        return slot[0] if slot and slot[1:] == (0, Team.BLU) else None

    # Разрешение (что показывать)

    # Карточка австралия (src/domain/preview/variant_card.py)

    def variant_game(self, team: Optional[str] = None) -> Optional[str]:
        from src.domain.preview import variant_card
        return variant_card.game(self, team)

    def variant_shown(self, team: Optional[str] = None) -> Optional[str]:
        from src.domain.preview import variant_card
        return variant_card.shown(self, team)

    def variant_display_texture(self) -> Optional[str]:
        """Текстура активного варианта (Australium) или None, если не активен

        У варианта своя карточка (`australium_mat_name`): что на ней лежит -
        своя правка либо игровой gold-кадр, - то и показывает кадр.
        `australium_user_tex` остался от работ, записанных до карточки"""
        if not self.australium_active:
            return None
        return self.variant_shown()

    def is_variant_material(self, mat: Optional[str]) -> bool:
        """Материал варианта (Australium) - карточка с той же геометрией, что у
        главного, но со своей текстурой"""
        return bool(mat and self.australium_mat_name
                    and mat.lower() == self.australium_mat_name.lower())

    def resolve_card(self, mat: str, hands_blu_view: bool = False) -> Optional[str]:
        """Текстура для карточки при текущей команде/стиле

        hands_blu_view - режим рук на BLU: нейтральный материал показываем
        пустым (= «общий, наследует RED»), пока ему не задана отдельная синяя
        """
        if self.is_variant_material(mat):
            return self.variant_shown()
        # Вариантный стиль (skin > 0): своя правка, иначе ОРИГИНАЛ этого стиля
        # (у гильотины Bloody - своя игровая текстура). Базу стиль не
        # наследует: карточка без собственной текстуры остаётся пустой
        if self.style_row and not is_decor(mat):
            return self.style_texture(self.style_row, mat)

        if hands_blu_view and not self.is_team_material(mat):
            return _existing(self.textures.get(Team.BLU, {}).get(mat))

        return self.resolve_base(mat)

    def original_card(self, mat: str) -> Optional[str]:
        """Игровой оригинал того, что сейчас на карточке, без правок человека:
        в стиле - оригинал стиля, у варианта - его игровой кадр"""
        if self.style_row and not is_decor(mat):
            return self._style_game(mat, self.style_row)
        if self.is_variant_material(mat):
            return self.variant_game()
        return self.game_base(mat)

    def style_texture(self, style: int, mat: str) -> Optional[str]:
        """Текстура материала в строке стиля: правка человека, иначе то, что
        под ней (оригинал стиля или красная при «Как красная»)"""
        return self.shown_at(mat, style, self.active_team)

    def style_upload_for(self, mat: str) -> Optional[str]:
        """Своя правка стиля под ИМЕНЕМ материала строки $texturegroup
        (``c_sd_cleaver_bloody``). Оригиналы стиля сюда не попадают: их
        сборка возьмёт из игры сама, если человек так ответит"""
        slot = self.build_slot(mat)
        return self.own_at(*slot) if slot and slot[1] else None

    def resolve_base(self, mat: str) -> Optional[str]:
        """Базовая (skin 0) текстура материала: пользовательская активной
        команды -> другая команда (нейтральные) -> игровой оригинал из VPK ->
        командный кадр для главного материала. Без учёта стилей (skin > 0)"""
        return self.shown_at(mat, 0, self.active_team)

    def game_base(self, mat: str, team: Optional[str] = None) -> Optional[str]:
        """Игровой оригинал материала - БЕЗ пользовательских правок

        Нужен склейке частей: картинки частей рисуются поверх игровой
        текстуры, а не поверх прошлой склейки. Иначе правки копились бы
        слоями, и «убрать картинку с части» ничего бы не возвращало

        `team` - чей оригинал, по умолчанию показанной команды. Сборке нужны
        обе: у RED и BLU своя краска в VMT
        """
        active = team or self.active_team
        base = self.part_cards.get(mat)
        if base and base != mat:
            return self.game_base(base, team)
        if is_decor(mat):
            return (_existing(self.decor_stock.get(active, {}).get(mat))
                    or _existing(self.decor_stock.get(Team.RED, {}).get(mat)))
        # Игровой оригинал текущей команды (карты ключуются RED-именами)
        vpk_map = self.vpk_red_tex_map if active == Team.RED else self.vpk_blu_tex_map
        g = _existing(vpk_map.get(mat))
        if g:
            return g

        # Нейтральные/служебные не зависят от команды - их оригинал только в
        # RED-карте, на BLU показываем его же (иначе «Прочее» на BLU пустое)
        if active != Team.RED and not self.is_team_material(mat):
            g = _existing(self.vpk_red_tex_map.get(mat))
            if g:
                return g

        # Главный материал без per-material карты: BLU пришёл одним кадром
        if self.material_names and mat == self.material_names[0]:
            frames = self.blu_frames if active == Team.BLU else self.red_frames
            if frames and os.path.exists(frames[0]):
                return frames[0]

        # Вариант (Australium): его игровой кадр приезжает отдельным сигналом,
        # в карты материалов он не попадает
        if self.is_variant_material(mat):
            return self.variant_game(active)

        return None

    def resolve_mesh(self, mat: str) -> Optional[str]:
        """
        Текстура для МЕША загруженного мода: правка пользователя, иначе
        оригинал из мода, с учётом команды

        Карточка меша - по связи из VMT (mod_mesh_cards). Без неё остаётся
        совпадение имён без учёта регистра
        """
        card = self.mod_mesh_cards.get((mat or '').lower())
        if variant_card.on_mesh(self, mat, card):
            return self.variant_display_texture()
        if card:
            # В стиле - своя текстура стиля (оригиналы стиля ключуются
            # материалом, правки - карточкой), иначе база: у стиля меняются
            # не все столбцы, и меш без своей пустел
            style = self.style_row
            styled = style and (self.style_texture(style, card)
                                or self.style_texture(style, mat))
            return styled or self.resolve_base(card)
        return (_existing(_lookup_ci(self.textures.get(self.active_team, {}), mat))
                or _existing(_lookup_ci(self.textures.get(Team.RED, {}), mat))
                or _existing(_lookup_ci(self.vpk_red_tex_map, mat)))

    def mod_uploads(self) -> Dict[str, str]:
        """
        Правки мода из VPK по его файлам: {карточка: путь}

        Синяя правка парной карточки хранится под КРАСНОЙ (как у игрового
        предмета), а в моде это другой VTF - отдаём её под именем синей
        карточки. Синяя без своей правки остаётся текстурой мода
        """
        red = self.textures.get(Team.RED, {})
        blu = self.textures.get(Team.BLU, {})
        out = {m: p for m, p in red.items()
               if m != SINGLE_TEX_KEY and not is_decor(m) and _existing(p)}
        for red_card, blu_card in self.blu_name_map.items():
            path = _existing(blu.get(red_card))
            if path and path != red.get(red_card):
                out[blu_card] = path
        out.update(variant_card.mod_blue_upload(self))
        return out

    # Что уходит в сборку

    def red_main(self) -> Optional[str]:
        """Пользовательская RED-текстура главного слота (без fallback на BLU)"""
        return _existing(self.textures.get(Team.RED, {}).get(self.storage_main_key()))

    def blu_main(self) -> Optional[str]:
        """Пользовательская BLU-текстура: главный слот, иначе любой BLU-слот"""
        blu = self.textures.get(Team.BLU, {})
        p = _existing(blu.get(self.storage_main_key()))
        if p:
            return p
        for mat, candidate in blu.items():
            # Огоньки гирлянды и материалы частей - свои карточки: синим
            # скином всего оружия они не станут
            if is_decor(mat) or mat in self.part_cards:
                continue
            p = _existing(candidate)
            if p:
                return p
        return None

    def uploaded_for_mat(self, mat: str) -> Optional[str]:
        """Загруженная пользователем текстура для материала (для сборки)

        Слот находит build_slot (пары имён, двойники, строки стилей), RED
        и BLU не смешиваются. Синее имя без пары (`{mat}_blue` у «сделать
        командным») берёт синюю под базой, затем главную BLU
        """
        side = variant_card.side_of(self, mat)    # золото - под карточкой австралия
        if side:
            return self.own_at(self.australium_mat_name, 0, side)
        slot = self.build_slot(mat)
        if slot and (slot[1] or self.blu_name_map or mat.lower() in self.blu_twins):
            return self.own_at(*slot)
        # Своя картинка под самим именем. То же одностороннее правило, что и
        # в показе (own_at): синяя на красный скин не уходит
        own = self.own_at(mat, 0, Team.RED)
        base, blue = team_form(mat)
        if own or not blue or self.blu_name_map:
            return own
        own = _existing(_lookup_ci(self.textures.get(Team.BLU, {}), base))
        plain = mat.lower().endswith(BLUE_SUFFIXES)
        # force_team без своей синей: красная - только если выбрано «Как
        # красная», иначе синяя игровая (build_answer) - как у игровой команды
        if (not own and self.force_team
                and self._like_key(self._card_of(base), 0) in self.blu_like_red):
            own = _existing(_lookup_ci(self.textures.get(Team.RED, {}), base))
        # Главная синяя - только самому синему скину, не праздничному `_blue_xmas`
        return own or (self.blu_main() if plain else None)

    def _card_of(self, mat: str) -> str:
        """Ключ карточки материала: у одноматериальной модели она одна и
        лежит под служебным ключом, а сборка спрашивает настоящее имя"""
        return SINGLE_TEX_KEY if self.material_names == [SINGLE_TEX_KEY] else mat

    def uploaded_slot_paths(self) -> Dict[str, str]:
        """{mat: path} всех заполненных слотов, активная команда приоритетнее.
        SINGLE_TEX_KEY пропускается (главная идёт в сборку отдельно)"""
        result: Dict[str, str] = {}
        for team in team_priority(self.active_team):
            for mat, path in self.textures.get(team, {}).items():
                # Золото собирается своим путём (variant_build_images): у него
                # картинка бывает и не своя (как обычная), и у команд разная
                if (mat == SINGLE_TEX_KEY or mat in result or is_decor(mat)
                        or self.is_variant_material(mat)):
                    continue
                if _existing(path):
                    result[mat] = path
        return result

    def blu_uploaded_paths(self) -> Dict[str, str]:
        """{mat: path} своих синих текстур (для командности рук при сборке)

        Нейтральная текстура лежит в обеих командах одной картинкой
        (set_texture), и такая копия - не своя синяя: по ней сборка делала
        нейтральные руки командными и писала лишний `_blue`-материал
        """
        red = self.textures.get(Team.RED, {})
        return {
            mat: path
            for mat, path in self.textures.get(Team.BLU, {}).items()
            if mat != SINGLE_TEX_KEY and not is_decor(mat) and _existing(path)
            and path != red.get(mat) and not self.is_variant_material(mat)
        }

    def decor_uploads(self) -> Dict[str, Dict[str, str]]:
        """Свои текстуры гирлянд: {карточка: {команда: путь}}

        Команда без своей правки берёт картинку другой, как и текстуры оружия
        (resolve_base): покрасили огоньки за RED - у BLU в игре те же. Иначе
        синие оставались игровыми, и в руках за BLU правка пропадала.
        Покрашенная отдельно команда остаётся своей
        """
        out: Dict[str, Dict[str, str]] = {}
        cards = {m for paths in self.textures.values() for m in paths if is_decor(m)}
        for card in sorted(cards):
            red = _existing(self.textures.get(Team.RED, {}).get(card))
            blu = _existing(self.textures.get(Team.BLU, {}).get(card))
            if red or blu:
                out[card] = {Team.RED: red or blu, Team.BLU: blu or red}
        return out

    # Снимок / восстановление (мини-память оружия)

    def snapshot(self) -> dict:
        """Глубокий снимок данных модели - для мгновенного восстановления
        оружия при возврате (без перезапуска воркера). Австралий-активность
        не сохраняется: после восстановления вариант всегда выключен"""
        return {
            'textures': {t: dict(d) for t, d in self.textures.items()},
            'material_names': list(self.material_names),
            'main_material': self.main_material,
            'active_team': self.active_team,
            'force_team': self.force_team,
            'blu_name_map': dict(self.blu_name_map),
            'blu_twins': dict(self.blu_twins),
            'blu_like_red': sorted(self.blu_like_red),
            'vpk_red_tex_map': dict(self.vpk_red_tex_map),
            'vpk_blu_tex_map': dict(self.vpk_blu_tex_map),
            'red_frames': list(self.red_frames),
            'blu_frames': list(self.blu_frames),
            'australium_frame': self.australium_frame,
            'australium_mat_name': self.australium_mat_name,
            'australium_user_tex': self.australium_user_tex,
            'australium_blu_frame': self.australium_blu_frame,
            'australium_blu_mat': self.australium_blu_mat,
        }

    def restore(self, snap: dict) -> None:
        """Восстанавливает данные модели из snapshot(). Стили (skin_overrides)
        в мини-память не входят - они живут в пер-стилевой памяти шапок;
        на всякий случай сбрасываем их, чтобы залипший active_skin не резолвил
        карточки восстановленного оружия в чужие override'ы"""
        self.reset_skins()
        self.textures = {t: dict(d) for t, d in (snap.get('textures') or {}).items()}
        self.material_names = list(snap.get('material_names') or [])
        self.main_material = snap.get('main_material')
        self.active_team = snap.get('active_team', Team.RED)
        self.force_team = snap.get('force_team', False)
        self.blu_name_map = dict(snap.get('blu_name_map') or {})
        self.blu_twins = dict(snap.get('blu_twins') or {})
        self.blu_like_red = set(snap.get('blu_like_red') or ())
        self.vpk_red_tex_map = dict(snap.get('vpk_red_tex_map') or {})
        self.vpk_blu_tex_map = dict(snap.get('vpk_blu_tex_map') or {})
        self.red_frames = list(snap.get('red_frames') or [])
        self.blu_frames = list(snap.get('blu_frames') or [])
        self.australium_frame = snap.get('australium_frame')
        self.australium_mat_name = snap.get('australium_mat_name')
        self.australium_user_tex = snap.get('australium_user_tex')
        self.australium_blu_frame = snap.get('australium_blu_frame')
        self.australium_blu_mat = snap.get('australium_blu_mat')
        self.australium_active = False

    # Сбросы

    def reset_skins(self) -> None:
        """Сброс стилей (skinfamilies) - при смене модели"""
        self.skin_info = None
        self.active_skin = 0
        self.skin_overrides = {}
        self.style_game_tex = {}

    def reset_team_data(self) -> None:
        """Сброс командных данных из VPK (кадры, карты, маппинг имён)"""
        self.red_frames = []
        self.blu_frames = []
        self.vpk_red_tex_map = {}
        self.vpk_blu_tex_map = {}
        self.blu_name_map = {}
        self.blu_twins = {}
        self.mod_mesh_cards = {}
        self.active_team = Team.RED
        self.force_team = False

    def reset_australium(self) -> None:
        """Сброс варианта Australium (кадр, своя текстура, активность)"""
        self.australium_frame = None
        self.australium_active = False
        self.australium_user_tex = None
        self.australium_mat_name = None
        self.australium_blu_frame = None
        self.australium_blu_mat = None
        self.variant_meshes = set()

    # Режим «Скайбокс»

    def resolve_skybox_face(self, face: str) -> Optional[str]:
        """Что показывает грань скайбокса: своя загруженная -> нарезка из
        панорамы -> стоковая грань выбранного неба"""
        return (_existing(self.textures.get(Team.RED, {}).get(face))
                or _existing(self.skybox_split_faces.get(face))
                or _existing(self.skybox_stock_faces.get(face)))

    def skybox_pano(self) -> Optional[str]:
        """Загруженная пользователем панорама (или None)"""
        from src.data.skyboxes import SKY_PANO_KEY
        return _existing(self.textures.get(Team.RED, {}).get(SKY_PANO_KEY))

    def skybox_build_data(self) -> dict:
        """Что уходит в сборку скайбокса: панорама + ручные оверрайды граней.
        Нарезанные превью-грани НЕ входят - сборка режет панораму заново в
        выбранном разрешении"""
        from src.data.skyboxes import SKY_FACES
        overrides = {}
        for face in SKY_FACES:
            p = _existing(self.textures.get(Team.RED, {}).get(face))
            if p:
                overrides[face] = p
        return {'equirect': self.skybox_pano(), 'face_overrides': overrides}

    def reset_skybox(self) -> None:
        """Сброс данных скайбокса (стоковые/нарезанные грани, загрузки
        пользователя живут в textures и чистятся общим сбросом слотов)"""
        self.skybox_stock_faces = {}
        self.skybox_split_faces = {}
