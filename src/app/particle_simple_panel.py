"""
Простой режим редактора частиц: крутилки выбранной системы и правки ими

Схема крутилок - services/simple_params_schema, чтение и запись атрибутов -
services/simple_params. Здесь то, что нужно странице поверх схемы: значение
из игры (для «как в игре»), адреса для живой правки превью, создание и
удаление модулей и быстрые правки всего эффекта одним шагом истории
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Dict, List, Optional

if TYPE_CHECKING:
    from src.app.particles_editor import ParticlesEditor

#: Во сколько раз меняет значения одно нажатие быстрой правки
QUICK_STEP = 1.25


def _plain(value):
    """Кортежи схемы -> списки JSON"""
    return list(value) if isinstance(value, tuple) else value


def effect_systems(get, root: str) -> Dict[str, dict]:
    """{система: её JSON} - корень и все дочерние по ссылкам children, без
    повторов и циклов. `get(имя)` отдаёт систему или None"""
    out: Dict[str, dict] = {}
    stack = [root]
    while stack:
        name = stack.pop()
        if name in out:
            continue
        sys_json = get(name)
        if sys_json is None:
            continue
        out[name] = sys_json
        stack.extend(c.get('childName', '') for c in sys_json.get('children') or [])
    return out


class SimplePanel:
    """Крутилки простого режима поверх открытого в редакторе PCF"""

    def __init__(self, editor: "ParticlesEditor") -> None:
        self._ed = editor

    def _root(self) -> str:
        paths = self._ed._host.tf2_paths()
        return '' if 'error' in paths else paths['root']

    def _stock_system(self, system: str) -> Optional[dict]:
        pcf = self._ed.pcf
        if not hasattr(pcf, 'stock_systems'):
            return None
        root = self._root()
        return (pcf.stock_systems(root) or {}).get(system) if root else None

    def params(self, system: str, lang: str = 'ru') -> List[dict]:
        """
        Крутилки для системы

        value=None - нужного модуля в системе нет: крутилку показывают
        бледной, первая правка модуль создаст. `stock` есть, только если
        игра знает эту систему: значение там (None - модуля в игре нет).
        `targets` - адреса атрибутов для живой правки превью
        """
        from src.data.translations import TRANSLATIONS
        from src.services import simple_params as sp

        pcf = self._ed.pcf
        sys_json = self._ed._one_system(system) if pcf else None
        if sys_json is None:
            return []
        stock = self._stock_system(system)
        t = TRANSLATIONS.get(lang, TRANSLATIONS['en'])
        out: List[dict] = []
        for p in sp.SIMPLE_PARAMS:
            row = {
                'key': p.key,
                'name': t.get(f'particles_sp_{p.key}', p.key),
                'hint': t.get(f'particles_sp_{p.key}_tip', ''),
                'kind': p.kind,
                'value': _plain(sp.read_param(sys_json, p)),
                'placeholder': _plain(p.placeholder_value),
                # Мягкие границы - для ползунка, жёсткие - предел ручного
                # ввода: в стоке встречаются emission_rate под миллион, и
                # запрет на них молча испортил бы чужой эффект
                'min': p.minimum, 'max': p.maximum,
                'hard_min': p.input_min, 'hard_max': p.input_max,
                'curve': p.curve,
                'decimals': p.decimals,
                'creatable': p.creatable,
                'ordered': p.ordered,
                'group': p.group,
                'group_name': t.get(f'particles_sp_group_{p.group}', p.group),
                'unit': t.get(f'particles_sp_unit_{p.unit}', '') if p.unit else '',
                'choices': [{'value': c, 'label': t.get(f'particles_sp_{p.key}_{c}', str(c))}
                            for c in p.choices],
                'targets': sp.targets(sys_json, p),
                'missing': [list(m) for m in sp.missing_modules(sys_json, p)],
            }
            if stock is not None:
                row['stock'] = _plain(sp.read_param(stock, p))
            out.append(row)
        return out

    def set(self, system: str, key: str, value: Any) -> Dict[str, Any]:
        """Пишет значение крутилки и отдаёт обновлённые системы"""
        from src.services import simple_params as sp

        pcf = self._ed.pcf
        if pcf is None:
            return {'error': 'PCF не загружен'}
        param = next((p for p in sp.SIMPLE_PARAMS if p.key == key), None)
        if param is None:
            return {'error': f'неизвестный параметр: {key}'}
        sys_json = self._ed._one_system(system)
        if sys_json is None:
            return {'error': f'система не найдена: {system}'}

        if param.kind == 'module':
            # Выключатель уже в нужном положении - пустой шаг истории не нужен
            if sp.read_param(sys_json, param) == bool(value):
                return self._reply(system, commit=False)
            err = self._toggle_module(system, sys_json, param, bool(value))
        else:
            err = self._write(system, sys_json, param, value)
        if err:
            # Часть модулей могла успеть добавиться: шаг истории всё равно
            # пишем, иначе Ctrl+Z их не уберёт
            if self._ed._one_system(system) != sys_json:
                self._ed._history_commit()
            return {'error': err}
        return self._reply(system)

    def _toggle_module(self, system: str, sys_json: dict, param, on: bool) -> str:
        """Крутилка-модуль: включить - добавить недостающие, выключить - убрать"""
        from src.services import simple_params as sp

        if on:
            return self._create(system, sys_json, param)
        pcf = self._ed.pcf
        for ref in param.refs:
            if ref.group is None:
                continue
            # Одноимённых модулей бывает несколько - убираем все, иначе
            # выключатель оставался бы включённым
            while (idx := sp.module_index(self._ed._one_system(system), ref.group,
                                          ref.function_name)) is not None:
                if not pcf.remove_module(system, ref.group, idx):
                    return f'не удалось убрать модуль {ref.function_name}'
        return ''

    def _create(self, system: str, sys_json: dict, param) -> str:
        """Недостающие модули крутилки и их начальные атрибуты (seed)"""
        from src.services import simple_params as sp

        # creatable=False - модуль создавать нельзя. У эмиттеров это не
        # придирка: добавленный emit_instantaneously задваивает залп
        if not param.creatable:
            return 'в этой системе нет модуля для этого параметра'
        pcf = self._ed.pcf
        made = sp.missing_modules(sys_json, param)
        for group, fn in made:
            if not pcf.add_module(system, group, fn, self._root()):
                return f'не удалось создать модуль {fn}'
        fresh = self._ed._one_system(system)
        for group, fn, attr, attr_type, v in param.seed:
            if (group, fn) not in made:
                continue
            idx = sp.module_index(fresh, group, fn)
            if idx is not None:
                pcf.ensure_attr(system, group, idx, attr, attr_type, _plain(v))
        return ''

    def _write(self, system: str, sys_json: dict, param, value) -> str:
        from src.services import simple_params as sp

        # Правка заготовки И ЕСТЬ включение параметра: модуля под ним ещё
        # нет, и создаём его сами. Отдельной кнопки «Включить» нет
        if sp.read_param(sys_json, param) is None:
            err = self._create(system, sys_json, param)
            if err:
                return err
            sys_json = self._ed._one_system(system)
        calls = sp.write_calls(sys_json, param, value)
        if not calls:
            return 'в этой системе нужного модуля нет'
        for group, idx, attr, attr_type, v in calls:
            self._ed.pcf.ensure_attr(system, group, idx, attr, attr_type, v)
        return ''

    def quick(self, system: str, kind: str, up: bool) -> Dict[str, Any]:
        """
        Быстрая правка всего эффекта: выбранная система и её дочерние

        Крутилки со степенью для `kind` (см. SimpleParam.scales) умножаются на
        QUICK_STEP в этой степени (или делятся). Меняется только то, что
        уже лежит в файле (simple_params.scale_calls): «крупнее» не должно
        добавлять эффекту модулей и атрибутов, которых в нём не было
        """
        from src.services import simple_params as sp
        from src.services.simple_params_schema import QUICK

        pcf = self._ed.pcf
        if pcf is None:
            return {'error': 'PCF не загружен'}
        if kind not in QUICK:
            return {'error': f'неизвестная правка: {kind}'}
        # Только системы эффекта, а не весь файл: у item_fx их 378
        systems = effect_systems(self._ed._one_system, system)
        if system not in systems:
            return {'error': f'система не найдена: {system}'}
        step = QUICK_STEP if up else 1 / QUICK_STEP
        touched = 0
        for name, sys_json in systems.items():
            for p in sp.SIMPLE_PARAMS:
                power = dict(p.scales).get(kind)
                if not power:
                    continue
                for group, idx, attr, attr_type, v in sp.scale_calls(
                        sys_json, p, step ** power):
                    pcf.ensure_attr(name, group, idx, attr, attr_type, v)
                    touched += 1
        if not touched:
            return {'error': 'в эффекте нечего менять'}
        return self._reply(system, touched=list(systems))

    def _reply(self, system: str, commit: bool = True,
               touched: Optional[List[str]] = None) -> Dict[str, Any]:
        """Шаг истории и изменённые системы для страницы"""
        return self._ed.edit_reply(system, touched or [system], commit=commit)
