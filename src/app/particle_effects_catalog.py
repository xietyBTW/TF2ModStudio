"""
Каталог эффектов игры для списка слева: поиск по имени, источники, разделы

Строки собираются раз на язык из индекса систем всех PCF, таблицы
источников и каталога необычных; дальше каждый запрос - проход по ним
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Dict, List, Optional

from src.shared.text_search import plain

if TYPE_CHECKING:
    from src.app.session import AppSession


#: Порядок разделов необычных - как в каталоге игры
CATEGORY_ORDER = {'cosmetic': 0, 'taunt': 1, 'weapon': 2, 'killstreak': 3,
                  'other': 4}
#: Раздел систем вида «необычный» без имени из игры: служебные и дочерние
UNNAMED = 'unnamed'


def with_weapon_variants(index: Dict[str, str], roots: Dict[str, str],
                         unusuals: List[dict]) -> Dict[str, str]:
    """Корни систем, где варианты оружейного необычного - дети его самого

    У оружейных эффектов в items_game стоит use_suffix_name: игра дописывает
    к имени particle_suffix оружия и зовёт weapon_unusual_hot_rocketlauncher
    (и _vm от первого лица). В PCF это отдельные корни без имени из игры, и в
    списке они расползались сотней строк «без названия» вместо «Жара»
    """
    heads = [fx['system'] for fx in unusuals if fx['category'] == 'weapon']
    if not heads:
        return roots
    out = dict(roots)
    for system in index:
        top = roots.get(system) or system
        low = top.lower()
        head = next((h for h in heads if low.startswith(h.lower() + '_')), '')
        if head:
            out[system] = head
    return out


#: Служебные поля строки: по ним ищут и раскладывают, странице они не нужны
_HIDDEN = ('blob', 'keys', 'root', 'matched')


def _strip(row: Dict[str, Any]) -> Dict[str, Any]:
    return {k: v for k, v in row.items() if k not in _HIDDEN and k != 'kids'}


class EffectCatalog:
    """Эффекты игры по имени и по тому, чем они вызываются"""

    def __init__(self, host: "AppSession") -> None:
        self._host = host
        #: {корень: [дети]} - для разворачивания и счётчиков
        self._children: Dict[str, List[str]] = {}

    #: Сколько эффектов отдаём под поиском: систем в игре десять тысяч
    EFFECTS_PAGE = 200

    def particle_effects(self, query: str = '', source: str = '',
                         lang: str = 'ru', category: str = '',
                         kids_of: Optional[str] = None) -> Dict[str, Any]:
        """Эффекты игры по имени и по тому, чем они вызываются:
        {ready, items, facets, categories}

        Без запроса и без источника - необычные эффекты с именами из игры
        (то, что ищут чаще всего). С источником - все системы этого вида
        (оружие, постройки, игрок…), подписанные предметом: «Огнемёт»,
        «Турель». С запросом - поиск по всем 10 тысячам систем 134 файлов,
        включая имена предметов: «огнемёт» находит его вспышку и пламя.
        `ready` - собран ли индекс систем, до того ищем только по именам.
        `category` - раздел необычных (cosmetic, taunt…, `unnamed` - без
        имени из игры), есть только у списков необычных. `kids_of` - вместо
        списка только дочерние этого эффекта (см. effect_kids)
        """
        from src.data import particle_sources as ps

        rows, ready = self._effect_rows(lang)
        source = (source or '').strip().lower()
        words = [plain(w) for w in (query or '').split() if plain(w)]

        by_name = {row['system']: row for row in rows}
        counts: Dict[str, int] = {}
        #: Корни на показ, в порядке первого совпадения: {корень: [дети]}
        found: Dict[str, List[Dict[str, Any]]] = {}
        matched: set = set()
        for row in rows:
            if words and not all(w in row['blob'] for w in words):
                continue
            if source and source not in row['kinds']:
                continue
            # Без запроса и источника - каталог: только необычные
            if not words and not source and not row['name']:
                continue
            matched.add(row['system'])
            # Дочерняя встаёт под свой корень: у эффекта из тридцати систем
            # человеку нужна одна строка, а не тридцать
            top = row['root'] or row['system']
            kids = found.setdefault(top, [])
            if row['root'] and by_name.get(top) is not None:
                kids.append(row)
        # Счётчики - по корням и по всей игре под запросом, а не по
        # показанному: из каталога необычных иначе нельзя было бы уйти в
        # «Оружие»
        for top in {r['root'] or r['system'] for r in rows
                    if not words or all(w in r['blob'] for w in words)}:
            for kind in self._root_kinds(by_name, top):
                counts[kind] = counts.get(kind, 0) + 1

        items: List[Dict[str, Any]] = []
        for top, kids in found.items():
            root = by_name.get(top)
            if root is None:
                continue
            # Совпал только корень - показываем всех его детей, чтобы было
            # что развернуть, совпали дети - только их.
            # `open` - раскрыть сразу: нашли только детей, а не корень;
            # когда совпал и корень, сотня раскрытых огнемётов - шум
            hit = bool(kids) and top not in matched
            if not kids and top in matched:
                kids = [by_name[k] for k in self._children.get(top, ())
                        if k in by_name]
            items.append({**root, 'kids': sorted(kids, key=lambda it: it['system'].lower()),
                          'matched': top in matched, 'open': hit})

        if words:
            # Совпавшие целиком или с начала - выше: «crit» это crit_text,
            # а не bullet_tracer01_crit. Корень наследует лучший ранг детей
            def rank_one(it: Dict[str, Any]) -> int:
                if any(w in it['keys'] for w in words):
                    return 0
                if any(k.startswith(w) for k in it['keys'] for w in words):
                    return 1
                return 2

            def rank(it: Dict[str, Any]) -> int:
                own = rank_one(it) if it['matched'] else 3
                return min([own, *(rank_one(k) for k in it['kids'])])
            items.sort(key=rank)
        elif source == 'unusual':
            # Необычные - разделами, как каталог: по предмету их не собрать,
            # у эффекта с именем подписи нет, и он уезжал в конец списка
            items.sort(key=lambda it: CATEGORY_ORDER.get(it['category'], 9))
        elif source:
            # Под источником - по предмету, потом по имени: все вспышки
            # огнемёта рядом
            items.sort(key=lambda it: (' '.join(it['labels']).lower() or '\uffff',
                                       it['system'].lower()))
        facets = [{'key': kind, 'name': name, 'count': counts.get(kind, 0)}
                  for kind, name in ps.KIND_NAMES.items()
                  if counts.get(kind) or kind == source]
        categories: List[Dict[str, Any]] = []
        if source == 'unusual' or not (words or source):
            items, categories = self._by_category(items, category)
        if kids_of is not None:
            found_item = next((it for it in items if it['system'] == kids_of), None)
            return {'kids': [_strip(k) for k in found_item['kids']] if found_item else []}
        # Без запроса список отдаём весь (необычных тысяча с небольшим, его
        # листают), поиск - первые двести: дальше уточняют запрос
        page = items if not words else items[:self.EFFECTS_PAGE]
        return {'ready': ready,
                'items': [self._listed(it, inline=bool(words) or it['open']) for it in page],
                'total': len(items), 'facets': facets, 'categories': categories}

    @staticmethod
    def _listed(item: Dict[str, Any], inline: bool) -> Dict[str, Any]:
        """Строка списка. Дочерние - только у раскрытых сразу (поиск): в
        каталоге они 88% ответа (1,3 из 1,5 МБ), а смотрят их единицы. Без
        них - число, по раскрытию страница спросит effect_kids"""
        row = {**_strip(item), 'kids_n': len(item['kids'])}
        row['kids'] = [_strip(k) for k in item['kids']] if inline else []
        return row

    def effect_kids(self, system: str, query: str = '', source: str = '',
                    lang: str = 'ru', category: str = '') -> List[Dict[str, Any]]:
        """Дочерние строки эффекта `system` - те же, что дал бы список с
        этими запросом, источником и разделом"""
        return self.particle_effects(query, source, lang, category, kids_of=system)['kids']

    @staticmethod
    def _by_category(items: List[Dict[str, Any]], category: str):
        """Разделы необычных со счётчиками и список выбранного раздела

        Счётчики - до выбора раздела, иначе из «Насмешек» не было бы видно,
        сколько в «Косметике». Выбранный раздел остаётся кнопкой, даже если
        под новым запросом он пуст
        """
        from src.data.unusual_effects import CATEGORY_NAMES

        key = lambda it: it['category'] or UNNAMED  # noqa: E731
        counts: Dict[str, int] = {}
        for it in items:
            counts[key(it)] = counts.get(key(it), 0) + 1
        names = {**CATEGORY_NAMES, UNNAMED: 'Без названия'}
        categories = [{'key': k, 'name': names[k], 'count': counts.get(k, 0)}
                      for k in sorted(names, key=lambda k: CATEGORY_ORDER.get(k, 9))
                      if counts.get(k) or k == category]
        if category:
            items = [it for it in items if key(it) == category]
        return items, categories

    def _root_kinds(self, by_name: Dict[str, dict], top: str) -> set:
        """Виды корня вместе с детьми: огнемёт зовёт эффект, у которого
        сам корень - «правила игры», а пламя - дети"""
        kinds = set(by_name[top]['kinds']) if top in by_name else set()
        for kid in self._children.get(top, ()):
            if kid in by_name:
                kinds.update(by_name[kid]['kinds'])
        return kinds

    def _effect_rows(self, lang: str):
        """Все эффекты игры со словами для поиска - один раз на язык

        Строка стоит подписей на двух языках и десятка словарных обращений;
        на десять тысяч систем это полсекунды, и делать это на каждую
        букву запроса нельзя. Пока индекс систем строится, строк только
        необычные - и кэш не ставится, чтобы дождаться остальных
        """
        from src.data import particle_sources as ps
        from src.data.hats_parser import parse_localization
        from src.data.unusual_effects import CATEGORY_NAMES
        from src.services.particle_editor_service import ParticleEditorService

        paths = self._host.tf2_paths()
        if 'error' in paths:
            return [], False
        index = ParticleEditorService.system_index(paths['root'])
        roots = ParticleEditorService.system_roots(paths['root'])
        cache = getattr(self, '_effect_cache', None)
        if cache and cache[0] == (lang, len(index)):
            return cache[1], bool(index)
        # Имя в items_game и в PCF бывает разного регистра (stamp_spin против
        # Stamp_spin в stamp_spin.pcf), а игра сравнивает без регистра. Берём
        # написание файла: иначе у эффекта не находился файл, и он не
        # открывался, а система файла шла второй строкой без имени
        spelled = {system.lower(): system for system in index}

        def as_in_file(effects: List[dict]) -> List[dict]:
            return [{**fx, 'system': spelled.get(fx['system'].lower(), fx['system'])}
                    for fx in effects]

        unusuals = as_in_file(self._unusual_effects(lang))
        pcf_roots, roots = roots, with_weapon_variants(index, roots, unusuals)
        #: {корень: [дети]} - для разворачивания и счётчиков
        self._children: Dict[str, List[str]] = {}
        for kid, top in roots.items():
            self._children.setdefault(top, []).append(kid)
        by_system = {fx['system']: fx for fx in unusuals}
        names = {fx['system']: fx['name'] for fx in unusuals if fx['name']}
        english = ({} if lang == 'en' else
                   {fx['system']: fx['name']
                    for fx in as_in_file(self._unusual_effects('en'))})
        loc = parse_localization(paths['root'],
                                 'russian' if lang == 'ru' else 'english')
        loc_en = loc if lang == 'en' else parse_localization(paths['root'], 'english')
        # Необычные - первыми и по категориям (так идёт каталог), остальные
        # системы - в порядке индекса
        pairs = [(fx['system'], index.get(fx['system'], ''))
                 for fx in sorted(unusuals,
                                  key=lambda fx: CATEGORY_ORDER.get(fx['category'], 9))]
        pairs += [(system, file) for system, file in index.items()
                  if system not in by_system]

        rows: List[Dict[str, Any]] = []
        for system, file in pairs:
            fx = by_system.get(system)
            name = fx['name'] if fx else ''
            labels = [l for l in ps.labels_of(system, file, loc, names, lang)
                      if l != name]
            labels_en = ps.labels_of(system, file, loc_en, english, 'en')
            rows.append({
                'system': system, 'file': file, 'name': name,
                # Эффект с именем из игры - сам себе корень, даже если в
                # файле он чей-то ребёнок: superrare_burning2 лежит под
                # superrare_test, а ищут его
                'root': '' if name else roots.get(system, ''),
                # Корень в самом PCF, если строка встала под другой: часть
                # варианта «Жара» под ракетомёт сворачивается под вариант
                'via': ('' if name or pcf_roots.get(system, '') == roots.get(system, '')
                        else pcf_roots.get(system, '')),
                'category': fx['category'] if fx else '',
                'category_name': CATEGORY_NAMES[fx['category']] if fx else '',
                # Эффект с именем из каталога необычных - необычный, даже
                # если таблица знает его по другому делу (Stamp_spin - «правила»)
                'kinds': [k for k in ps.KIND_NAMES
                          if k in ps.kinds_of(system, file) or (fx and k == 'unusual')],
                'labels': labels,
                'blob': ' '.join(plain(t) for t in
                                 (system, name, english.get(system, ''),
                                  *labels, *labels_en)),
                'keys': [plain(t) for t in (system, name, *labels) if t],
            })
        if index:
            self._effect_cache = ((lang, len(index)), rows)
        return rows, bool(index)

    def _unusual_effects(self, lang: str) -> List[dict]:
        """Таблица необычных эффектов с именами на языке интерфейса"""
        from src.data import unusual_effects
        from src.data.hats_parser import parse_localization
        from src.data.weapon_model_index import get_items_game_path

        cache = getattr(self, '_unusual_cache', None)
        if cache is None:
            cache = self._unusual_cache = {}
        if lang not in cache:
            paths = self._host.tf2_paths()
            items_game = get_items_game_path(paths['root'])
            try:
                text = open(items_game, encoding='utf-8', errors='replace').read()
            except OSError:
                text = ''
            loc = parse_localization(paths['root'],
                                     'russian' if lang == 'ru' else 'english')
            cache[lang] = unusual_effects.parse(text, loc)
        return cache[lang]
