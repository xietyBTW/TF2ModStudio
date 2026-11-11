"""
Декларативная схема «простого режима» редактора частиц

Каждый SimpleParam - одна крутилка: что она показывает и в какие атрибуты
каких модулей пишет. Добавление новой крутилки = одна запись в SIMPLE_PARAMS
плюс переводы particles_sp_<key>; UI строится по схеме автоматически,
синхронизация с деревом экспертного режима бесплатна - оба пути пишут через
ParticleEditorService.set_attr/ensure_attr и читают один systems_json

Три вещи, которые схема описывает явно, потому что данные игры этого требуют:

* ВАРИАНТЫ адресов (`variants`). Один и тот же смысл в разных эффектах
  живёт в разных модулях: скорость разлёта - либо в Position Within Sphere
  Random, либо в Velocity Random. Крутилка берёт первый вариант, все модули
  которого есть в системе.
* МЯГКИЕ и ЖЁСТКИЕ границы. minimum/maximum - диапазон ползунка (столько,
  сколько нужно в 99% эффектов), hard_min/hard_max - предел ручного ввода.
  Стоковые PCF содержат emission_rate до 999999 и lifetime до 1e10 («вечная»
  частица): если ограничить ввод мягкой границей, редактор молча испортит
  чужой эффект.
* КРИВАЯ ползунка. Половина стоковых значений гравитации лежит в ±50 при
  размахе ±800 - на линейном ползунке это 6% хода. Кривая «sqrt» отдаёт
  малым значениям половину дорожки

Логика чтения/записи тестируется напрямую
"""

import math
from dataclasses import dataclass
from typing import List, Optional, Tuple

#: Кривые ползунка: доля хода [0..1] ⇄ доля диапазона [0..1]
CURVE_LINEAR = "linear"
#: Квадратичная: мелкие значения занимают половину дорожки. Для диапазонов
#: «от нуля вверх» с длинным хвостом (скорость, область спавна, размер)
CURVE_SQRT = "sqrt"
#: То же, но симметрично относительно нуля - для знаковых (гравитация, спин)
CURVE_SIGNED_SQRT = "signed_sqrt"


@dataclass(frozen=True)
class AttrRef:
    """Адрес атрибута: (группа, functionName модуля) либо group=None -
    атрибут самой системы"""
    group: Optional[str]
    function_name: str
    attr: str
    attr_type: str                    # DMX-тип для создания атрибута
    component: Optional[int] = None   # компонента vec3 (напр. 2 = Z гравитации)
    #: В атрибуте лежит значение крутилки, умноженное на это. Доля жизни
    #: 0..1 показывается процентами (0.01), «от» случайной силы - минусом
    scale: float = 1.0


#: Виды крутилок, у которых одно значение (а не пара)
SINGLE_KINDS = ("value", "color", "bool", "choice")
#: Все виды. "module" - не атрибут, а наличие модуля: включить = добавить
KINDS = SINGLE_KINDS + ("range", "color_pair", "module")


@dataclass(frozen=True)
class SimpleParam:
    key: str            # ключ перевода particles_sp_<key>
    kind: str           # один из KINDS
    #: Адреса по приоритету: первый вариант, чьи модули есть в системе.
    #: Кнопка «Включить» создаёт модули ПЕРВОГО варианта
    variants: Tuple[Tuple[AttrRef, ...], ...]
    minimum: float = 0.0     # мягкая граница - диапазон ползунка
    maximum: float = 1.0
    hard_min: Optional[float] = None   # предел ручного ввода; None = minimum
    hard_max: Optional[float] = None
    curve: str = CURVE_LINEAR
    decimals: int = 2
    default: float = 0.0     # значение-заглушка, если атрибута ещё нет
    creatable: bool = True   # недостающий модуль можно создать кнопкой
    #: Раздел панели (particles_sp_group_<group>): крутилки одной природы рядом
    group: str = "emit"
    #: Диапазон «от - до»: начало не больше конца. У «начало - конец» (рост
    #: размера) концы независимы - частица может и усыхать
    ordered: bool = True
    #: Подпись единицы после числа (particles_sp_unit_<unit>), пусто - без
    unit: str = ""
    #: Значения выбора ("choice"): подписи - particles_sp_<key>_<значение>
    choices: Tuple[int, ...] = ()
    #: Что крутят «быстрыми правками» всего эффекта: {правка: степень}.
    #: Значение умножается на множитель правки в этой степени
    scales: Tuple[Tuple[str, float], ...] = ()
    #: Что выставить в только что созданном модуле, кроме самой крутилки:
    #: ((группа, функция, атрибут, тип, значение), ...). Шаблон модуля
    #: берётся из первого попавшегося стокового эффекта, и без этого новая
    #: «закрутка» вертелась бы вокруг его оси X, а не вокруг вертикали
    seed: Tuple[Tuple[str, str, str, str, object], ...] = ()

    @property
    def refs(self) -> Tuple[AttrRef, ...]:
        """Основной вариант адресов (тот, что создаёт кнопка «Включить»)"""
        return self.variants[0]

    @property
    def placeholder_value(self):
        """Что показывать в строке, под которой модуля ещё нет

        Умолчание Source: строка-заготовка обязана врать как можно меньше -
        именно это значение эффект и получит, если правку не трогать
        """
        if self.kind in ("value", "choice"):
            return self.default
        if self.kind in ("bool", "module"):
            return bool(self.default)
        if self.kind == "color":
            return [255, 255, 255, 255]
        if self.kind == "color_pair":
            return ([255, 255, 255, 255], [255, 255, 255, 255])
        return tuple(self.default for _ in range(self.slots))

    @property
    def slots(self) -> int:
        """Сколько значений у крутилки: у одиночной на них может работать
        несколько адресов (сила по трём осям), у пары - по адресу на конец"""
        return 1 if self.kind in SINGLE_KINDS or self.kind == "module" else 2

    @property
    def input_min(self) -> float:
        return self.minimum if self.hard_min is None else self.hard_min

    @property
    def input_max(self) -> float:
        return self.maximum if self.hard_max is None else self.hard_max


def curve_fraction(param: SimpleParam, value: float) -> float:
    """Значение -> доля хода ползунка [0..1] (обратное к curve_value)"""
    lo, hi = param.minimum, param.maximum
    span = hi - lo
    if span <= 0:
        return 0.0
    t = min(1.0, max(0.0, (value - lo) / span))
    if param.curve == CURVE_SQRT:
        return t ** 0.5
    if param.curve == CURVE_SIGNED_SQRT:
        signed = t * 2.0 - 1.0                      # [-1..1] от середины
        return ((abs(signed) ** 0.5) * (1 if signed >= 0 else -1) + 1.0) / 2.0
    return t


def curve_value(param: SimpleParam, fraction: float) -> float:
    """Доля хода ползунка [0..1] -> значение параметра"""
    f = min(1.0, max(0.0, fraction))
    if param.curve == CURVE_SQRT:
        t = f * f
    elif param.curve == CURVE_SIGNED_SQRT:
        signed = f * 2.0 - 1.0
        t = (signed * abs(signed) + 1.0) / 2.0
    else:
        t = f
    return param.minimum + (param.maximum - param.minimum) * t


def module_index(sys_json: dict, group: str,
                 function_name: str) -> Optional[int]:
    """Индекс первого модуля группы с таким functionName; None - нет такого

    Регистр written-имени в PCF гуляет от файла к файлу (в стоке есть и
    «Radius Random», и «radius_random»), поэтому сравнение регистронезависимое
    """
    for i, mod in enumerate(sys_json.get(group) or []):
        if mod.get("functionName", "").strip().lower() == function_name.lower():
            return i
    return None


def _refs_present(sys_json: dict, refs: Tuple[AttrRef, ...]) -> bool:
    """Все ли модули варианта есть в системе (системные атрибуты - всегда)"""
    return all(ref.group is None
               or module_index(sys_json, ref.group, ref.function_name) is not None
               for ref in refs)


def active_refs(sys_json: dict, param: SimpleParam) -> Tuple[AttrRef, ...]:
    """Вариант адресов, которым крутилка работает с ЭТОЙ системой

    Первый вариант, все модули которого на месте, если ни один не подходит -
    основной (его и будет создавать кнопка «Включить»)
    """
    for refs in param.variants:
        if _refs_present(sys_json, refs):
            return refs
    return param.refs


def _read_ref(sys_json: dict, ref: AttrRef):
    """Значение атрибута по адресу; None - модуля/атрибута нет"""
    if ref.group is None:
        tv = sys_json["attrs"].get(ref.attr)
    else:
        idx = module_index(sys_json, ref.group, ref.function_name)
        if idx is None:
            return None
        tv = sys_json[ref.group][idx]["attrs"].get(ref.attr)
    if tv is None:
        return None
    v = tv["v"]
    if ref.component is not None:
        try:
            return v[ref.component]
        except (TypeError, IndexError):
            return None
    return v


def _slot(param: SimpleParam, n: int) -> int:
    """Какому значению крутилки служит n-й адрес варианта"""
    return 0 if param.slots == 1 else n


def _from_attr(param: SimpleParam, ref: AttrRef, raw):
    """Значение атрибута -> значение крутилки (масштаб, тип)"""
    if param.kind == "bool":
        return bool(raw)
    if isinstance(raw, (int, float)) and not isinstance(raw, bool) and ref.scale != 1.0:
        return raw / ref.scale
    return raw


def _to_attr(param: SimpleParam, ref: AttrRef, value, attr_type: str = ""):
    """Значение крутилки -> значение атрибута"""
    if param.kind == "bool":
        return bool(value)
    if param.kind in ("color", "color_pair"):
        return list(value)
    v = value * ref.scale if ref.scale != 1.0 else value
    return int(round(v)) if (attr_type or ref.attr_type) == "integer" else v


def _stored_type(sys_json: dict, ref: AttrRef) -> str:
    """Тип атрибута в файле, если он там есть, иначе - из схемы

    Запись берёт тип, который у атрибута уже есть (attr_edit), и целое
    в файле обрезает дробь. Превью и запись должны считать одинаково
    """
    if ref.group is None:
        tv = sys_json["attrs"].get(ref.attr.lower()) or sys_json["attrs"].get(ref.attr)
    else:
        idx = module_index(sys_json, ref.group, ref.function_name)
        attrs = sys_json[ref.group][idx]["attrs"] if idx is not None else {}
        tv = attrs.get(ref.attr.lower()) or attrs.get(ref.attr)
    return (tv or {}).get("t") or ref.attr_type


def _step_number(param: SimpleParam, ref: AttrRef, raw, factor: float, integer: bool,
                 vector: bool = False):
    """Одно число атрибута после быстрой правки

    Считается в единицах крутилки (с её жёсткими границами) и переводится
    обратно. Целое сдвигается хотя бы на единицу - иначе 1 и 2 частицы за
    залп не менялись бы ни в какую сторону. Ноль остаётся нулём: у
    длительности это «бесконечно»
    """
    if not isinstance(raw, (int, float)) or isinstance(raw, bool) or not raw:
        return raw
    v = raw / ref.scale
    x = v * factor
    if integer or param.decimals == 0:
        mag, was = abs(x), abs(v)
        if factor > 1:
            mag = max(math.ceil(mag), was + 1)
        else:
            # Целое не уходит в ноль: залп в одну частицу «реже» - всё ещё залп
            mag = max(min(math.floor(mag), was - 1), min(was, 1))
        x = math.copysign(mag, v)
    if vector:
        # Оси вектора бывают любого знака - держим только величину
        top = max(abs(param.input_min), abs(param.input_max))
        x = max(-top, min(top, x))
    else:
        x = min(param.input_max, max(param.input_min, x))
    out = x * ref.scale
    return int(round(out)) if integer else out


def scale_calls(sys_json: dict, param: SimpleParam, factor: float) -> List[tuple]:
    """
    Быстрая правка: атрибуты крутилки, умноженные на `factor`, как вызовы
    ensure_attr. Только то, что уже лежит в файле: недостающий атрибут игра
    держит в дефолте, и дописывать его - раздувать PCF и метить систему
    изменённой. Компоненты вектора умножаются каждая сама: у хаотичной силы
    (-5,-5,0)..(5,5,100) «крупнее» не должно терять снос вверх
    """
    refs = active_refs(sys_json, param)
    if param.kind not in ("value", "range") or not _refs_present(sys_json, refs):
        return []
    calls: List[list] = []
    vectors: dict = {}
    for ref in refs:
        whole = _read_ref(sys_json, AttrRef(ref.group, ref.function_name,
                                             ref.attr, ref.attr_type))
        if whole is None:
            continue
        idx = 0 if ref.group is None else module_index(sys_json, ref.group,
                                                       ref.function_name)
        integer = _stored_type(sys_json, ref) == "integer"
        if ref.component is None:
            calls.append([ref.group, idx, ref.attr, _stored_type(sys_json, ref),
                          _step_number(param, ref, whole, factor, integer)])
            continue
        if not isinstance(whole, (list, tuple)) or ref.component >= len(whole):
            continue
        # Вектор умножается целиком, а не только ось крутилки: гравитация
        # или подъём со сносом вбок сохраняют направление
        key = (ref.group, idx, ref.attr)
        if key not in vectors:
            vectors[key] = [_step_number(param, ref, c, factor, False, vector=True)
                            for c in whole]
            calls.append([ref.group, idx, ref.attr, ref.attr_type, vectors[key]])
    return [tuple(c) for c in calls]


def read_param(sys_json: dict, param: SimpleParam):
    """
    Текущее значение крутилки из systems_json

    Returns:
        одиночная -> значение; "range"/"color_pair" -> кортеж из двух;
        "module" -> есть ли модуль. None - нужного модуля в системе нет
        (крутилка бледная, первая правка его создаст). Отсутствующий АТРИБУТ
        существующего модуля - не причина выключать: игра держит его в
        дефолте, и правка его создаст
    """
    refs = active_refs(sys_json, param)
    present = _refs_present(sys_json, refs)
    if param.kind == "module":
        return present
    if not present:
        return None
    ph = param.placeholder_value
    vals = [ph] if param.slots == 1 else list(ph)
    seen = set()
    for n, ref in enumerate(refs):
        slot = _slot(param, n)
        if slot in seen:
            continue                       # у одиночной правит первый адрес
        seen.add(slot)
        raw = _read_ref(sys_json, ref)
        if raw is not None:
            vals[slot] = _from_attr(param, ref, raw)
    return vals[0] if param.slots == 1 else tuple(vals)


def missing_modules(sys_json: dict, param: SimpleParam) -> List[tuple]:
    """[(группа, functionName)] модулей, которых не хватает крутилке"""
    out = []
    for ref in active_refs(sys_json, param):
        if ref.group is None:
            continue
        if module_index(sys_json, ref.group, ref.function_name) is None:
            if (ref.group, ref.function_name) not in out:
                out.append((ref.group, ref.function_name))
    return out


def targets(sys_json: dict, param: SimpleParam) -> List[dict]:
    """Куда крутилка пишет в ЭТОЙ системе: [{slot, group, index, attr,
    component, scale, type}]. Пусто - модуля нет

    Нужно странице для живой правки: пока тянут ползунок, превью меняет
    атрибуты у себя, не дожидаясь Python
    """
    if param.kind == "module":
        return []
    refs = active_refs(sys_json, param)
    out = []
    for n, ref in enumerate(refs):
        idx = 0
        if ref.group is not None:
            idx = module_index(sys_json, ref.group, ref.function_name)
            if idx is None:
                return []
        out.append({"slot": _slot(param, n), "group": ref.group, "index": idx,
                    "attr": ref.attr.lower(), "component": ref.component,
                    "scale": ref.scale,
                    "type": (ref.attr_type if ref.component is not None
                             else _stored_type(sys_json, ref))})
    return out


def write_calls(sys_json: dict, param: SimpleParam, value) -> List[tuple]:
    """
    Значение крутилки -> [(group|None, mod_idx, attr, attr_type, new_value)]
    для ParticleEditorService.ensure_attr. Пусто - нужного модуля нет

    Несколько компонент одного вектора (сила по трём осям) собираются в один
    вызов: по отдельности каждый следующий затирал бы предыдущий
    """
    refs = active_refs(sys_json, param)
    vals = [value] if param.slots == 1 else list(value)
    calls: List[list] = []
    vectors: dict = {}
    for n, ref in enumerate(refs):
        idx = 0
        if ref.group is not None:
            idx = module_index(sys_json, ref.group, ref.function_name)
            if idx is None:
                return []
        v = _to_attr(param, ref, vals[_slot(param, n)],
                     "" if ref.component is not None else _stored_type(sys_json, ref))
        if ref.component is None:
            calls.append([ref.group, idx, ref.attr, ref.attr_type, v])
            continue
        key = (ref.group, idx, ref.attr)
        if key not in vectors:
            cur = _read_ref(sys_json, AttrRef(
                ref.group, ref.function_name, ref.attr, ref.attr_type))
            base = list(cur) if isinstance(cur, (list, tuple)) else [0.0, 0.0, 0.0]
            vectors[key] = base
            calls.append([ref.group, idx, ref.attr, ref.attr_type, base])
        vectors[key][ref.component] = v
    return [tuple(c) for c in calls]


def _r(group, fn, attr, attr_type="float", component=None, scale=1.0) -> AttrRef:
    return AttrRef(group, fn, attr, attr_type, component, scale)


def _v(*refs: AttrRef) -> Tuple[AttrRef, ...]:
    """Один вариант адресов"""
    return refs


# Схема - отдельным файлом: логика выше от неё не зависит, а сама схема
# растёт с каждой крутилкой
from src.services.simple_params_schema import SIMPLE_PARAMS  # noqa: E402,F401
