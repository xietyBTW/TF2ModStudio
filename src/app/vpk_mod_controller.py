"""
Показ чужого мода из VPK: воркер разбора и то, что из него следует сеансу

Тот же контракт, что у остальных контроллеров превью (preview_controller):
сначала состояние сеанса, потом своё событие
"""

from __future__ import annotations

from src.domain.preview.session import PreviewSession
from src.services.base_worker import Signal
from src.shared.constants import Team


class VpkModController:
    """
    Показ ЧУЖОГО мода из VPK: его модель и его текстуры

    Отличие от обычной загрузки - источник. Геометрия и материалы берутся из
    файла пользователя, а карточки строятся по VTF мода, а не по материалам
    игровой модели. Поэтому у сеанса поднимается custom_vpk_mode: обычная
    фильтрация материалов эти карточки перетёрла бы
    """

    progress = Signal(str)
    ready = Signal(str, str)           # (obj_path, texture_path)
    animated = Signal(object, float)
    cards = Signal(object)             # [{name, display_name, preview_png}]
    materials = Signal(object)         # имена материалов модели (меши)
    skins = Signal(object)             # стили модели (skinfamilies)
    #: (ключ оружия, reference SMD мода) - что мод заменяет. По нему страница
    #: открывает вид от первого лица: мод показывается в руках класса
    weapon = Signal(str, str)
    sky = Signal(object)               # {грань: карточка} - мод неба
    links = Signal()                   # меши и команды мода связаны с карточками
    failed = Signal(str)

    def __init__(self, session: PreviewSession):
        self._session = session
        self._worker = None

    def stop(self) -> None:
        """Не ждёт: у воркера своя временная папка, делить ему с новым нечего"""
        if self._worker is not None:
            self._worker.cancel()
            self._worker = None

    def load(self, user_vpk: str, misc_vpk: str, textures_vpk: str,
             lang: str = 'en', model: str = '') -> None:
        """Начинает разбор мода. Состояние сеанса чистится ДО загрузки

        `model` - какую модель мода показать (путь MDL в VPK); пусто - само
        оружие или первую
        """
        self.stop()

        s = self._session
        s.reset_skins()
        s.reset_team_frames()
        s.reset_misc()
        # Режим включается ПОСЛЕ сбросов: reset_team_frames его гасит
        s.custom_vpk_mode = True
        s.custom_model_materials = []
        s.reset_custom_vpk()

        from src.services.preview_vpk_mod_worker import PreviewVpkModWorker
        w = PreviewVpkModWorker(
            user_vpk_path=user_vpk,
            misc_vpk_path=misc_vpk,
            textures_vpk_path=textures_vpk,
            lang=lang,
            model=model,
        )
        w.progress.connect(self.progress.emit)
        w.ready.connect(self._on_ready)
        w.animated.connect(self._on_animated)
        w.cards_ready.connect(self._on_cards)
        w.materials_ready.connect(self._on_materials)
        w.skins_ready.connect(self._on_skins)
        w.weapon_found.connect(self._on_weapon)
        w.sky_ready.connect(self._on_sky)
        w.unused.connect(self._on_unused)
        w.replaced.connect(self._on_replaced)
        w.links_ready.connect(self._on_links)
        w.failed.connect(self.failed.emit)
        self._worker = w
        w.start()

    def _on_links(self, meshes: dict, blue: dict) -> None:
        """
        Меши -> карточки и командные пары мода

        Синяя карточка уходит из ряда и становится синей стороной красной:
        переключатель команды показывает её на месте красной, как у игрового
        предмета. Огоньки гирлянды RED и BLU раньше стояли в ряду рядом
        """
        t = self._session.textures
        t.mod_mesh_cards = {str(m).lower(): c for m, c in (meshes or {}).items()}
        blue = {r: b for r, b in (blue or {}).items() if r in t.material_names}
        if blue:
            t.blu_name_map = dict(blue)
            t.vpk_blu_tex_map = {r: t.vpk_red_tex_map[b] for r, b in blue.items()
                                 if b in t.vpk_red_tex_map}
            gone = set(blue.values())
            t.material_names = [n for n in t.material_names if n not in gone]
            if t.main_material in gone:
                t.main_material = t.material_names[0] if t.material_names else None
            red, blu = t.textures.setdefault(Team.RED, {}), t.textures.setdefault(Team.BLU, {})
            for r, b in blue.items():
                # До пары красная карточка считалась общей и лежала копией и
                # за BLU (восстановленная работа, правка до разбора). Копия -
                # не своя синяя: иначе красная правка ложилась на синий VTF мода
                if r in blu and blu[r] == red.get(r):
                    del blu[r]
                # Правка, сделанная раньше прямо на синей карточке, - синяя
                # сторона красной
                old = red.pop(b, None) or blu.get(b)
                blu.pop(b, None)
                if old:
                    blu[r] = old
        self.links.emit()

    def _on_unused(self) -> None:
        self._session.custom_vpk_unused = True

    def _on_replaced(self, kind: str, mdl: str, own_smd: str) -> None:
        """Что мод заменяет. Своя модель мода - её reference SMD: на персонаже
        шапка мода надевается ею, а не игровой"""
        s = self._session
        s.custom_vpk_kind = kind or ''
        s.custom_vpk_mdl = mdl or ''
        s.custom_vpk_smd = own_smd or None

    def _on_sky(self, faces: dict) -> None:
        """Мод - небо: какие карточки на каких гранях"""
        self._session.custom_vpk_sky = dict(faces or {})
        self.sky.emit(dict(faces or {}))

    def _on_weapon(self, key: str, ref_smd: str, own_model: bool = True) -> None:
        """Мод опознан: чьё это оружие, где его меш и свой ли он"""
        self._session.custom_vpk_weapon = key or None
        self._session.custom_vpk_smd = ref_smd or None
        self._session.custom_vpk_own_model = bool(own_model)
        self.weapon.emit(key or '', ref_smd or '')

    # Сигналы воркера: сначала сессия, потом событие

    def _on_ready(self, obj_path: str, texture_path: str) -> None:
        s = self._session
        s.textures.active_team = Team.RED
        if texture_path:
            s.textures.red_frames = [texture_path]
        s.current_object = ('custom_vpk', obj_path, texture_path)
        self.ready.emit(obj_path, texture_path)

    def _on_animated(self, frames: list, framerate: float) -> None:
        if not frames:
            return
        self._session.textures.red_frames = list(frames)
        self._session.team_framerate = framerate
        self.animated.emit(frames, framerate)

    def _on_cards(self, cards: list) -> None:
        """
        Карточки мода. Превью его текстур кладём как ОРИГИНАЛЫ (vpk_red_tex_map)

        Так нетронутая карточка остаётся текстурой мода и в сборку как
        пользовательская не уходит, своё изображение перекроет её обычным
        путём - через textures[RED]
        """
        import os

        cards = list(cards or [])
        if not cards:
            return
        s = self._session
        names = [c['name'] for c in cards if c.get('name')]
        s.textures.material_names = names
        s.textures.main_material = names[0] if names else None
        for card in cards:
            png = card.get('preview_png')
            if png and os.path.exists(png):
                s.textures.vpk_red_tex_map[card['name']] = png
        # Карты, что уже есть в VMT мода: диалог карт покажет их отмеченными
        s.mod_maps = {c['name']: c['maps'] for c in cards if c.get('name') and c.get('maps')}
        s.mod_vmts = {c['name']: c['vmt_path'] for c in cards
                      if c.get('name') and c.get('vmt_path')}
        self.cards.emit(cards)

    def _on_materials(self, materials: list) -> None:
        if not materials:
            return
        s = self._session
        s.custom_model_materials = list(materials)
        # Карточки шли по путям VTF в архиве, и первой бывала чужая текстура
        # (огоньки гирлянды из того же мода). Главная - материал самой модели:
        # на неё ложатся War Paint и части одноматериальной модели
        # Карточка материала - по связи из VMT (paper_hat -> paper_hat_color),
        # иначе по имени
        links = s.textures.mod_mesh_cards
        order = [links.get(m.lower(), m).lower() for m in materials]
        names = s.textures.material_names
        # В порядке модели: у ракетомёта со вшитой гирляндой главной вставали
        # огоньки, а не он сам
        first = sorted((n for n in names if n.lower() in order),
                       key=lambda n: order.index(n.lower()))
        if first:
            s.textures.material_names = first + [n for n in names if n not in first]
            s.textures.main_material = first[0]
        self.materials.emit(materials)

    def _on_skins(self, info: dict) -> None:
        """
        У мода нашлись стили (skinfamilies)

        Мало запомнить их наличие: у мода СВОИ текстуры стилей, и без них
        переключение стиля показывало бы пустые карточки вместо того, что
        лежит в файле. Раскладываем их переопределениями - так же, как это
        делает панель приложения (``_on_vpk_mod_skins_ready``)
        """
        s = self._session
        s.textures.skin_info = info or None

        s.adopt_style_textures((info or {}).get('skin_textures') or {})
        self.skins.emit(info)
