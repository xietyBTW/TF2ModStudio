"""Иерархия систем и контрольные точки - чистые функции над systems_json"""

from typing import Dict, List, Optional, Tuple

from src.services.particle_editor.pcf_format import MODULE_GROUPS


def flatten_hierarchy(tree: list) -> List[str]:
    """Имена из дерева сверху вниз, каждое по одному разу"""
    out, seen = [], set()

    def walk(nodes):
        for name, kids in nodes:
            if name not in seen:
                seen.add(name)
                out.append(name)
            walk(kids)

    walk(tree)
    return out


#: Сколько контрольных точек знает движок Source (MAX_PARTICLE_CONTROL_POINTS)
MAX_CONTROL_POINTS = 64


#: Имена атрибутов, которые НЕ являются номером контрольной точки, хотя и
#: содержат нужные слова: это границы диапазонов и счётчики (в стоке там
#: встречаются 20/30/40 - за пределами реальных CP эффекта)
_NOT_CP_ATTRS = ("maximum end control point", "# of control points to set",
                 "control point movement distance tolerance",
                 "control point offset for fast collisions",
                 "emission count scale control point field")


def _control_point_refs(sys_json: dict, systems: Optional[dict]
                        ) -> Tuple[List[Tuple[int, str, str]], set]:
    """Ссылки модулей на точки: [(номер, функция модуля, атрибут)] и точки,
    которые эффект расставляет сам. Общий обход для номеров и их ролей"""
    refs: List[Tuple[int, str, str]] = []
    # Точки, которые эффект расставляет САМ (Set child control points from
    # particle positions, Set control point positions): снаружи они не нужны,
    # и подсказка «нужны 0, 1, 2, 3» у анюжуала шапки заставляла искать, куда
    # девать 1-3, хотя игра даёт ему только точку 0
    own: set = set()
    seen: set = set()
    pending = [sys_json]
    while pending:
        s = pending.pop()
        if s is None or id(s) in seen:
            continue
        seen.add(id(s))
        for group in MODULE_GROUPS:
            for mod in s.get(group) or []:
                own.update(_self_set_control_points(mod))
                fn = mod.get("functionName") or ""
                for name, tv in (mod.get("attrs") or {}).items():
                    low = name.lower()
                    if "control point" not in low and "control_point" not in low:
                        continue
                    if any(low == skip or low.startswith(skip)
                           for skip in _NOT_CP_ATTRS):
                        continue
                    v = tv.get("v")
                    if isinstance(v, bool) or not isinstance(v, int):
                        continue
                    if 0 <= v < MAX_CONTROL_POINTS:
                        refs.append((v, fn, name))
        if systems:
            for ch in s.get("children") or []:
                pending.append(systems.get(ch.get("childName")))
    return refs, own


def referenced_control_points(sys_json: dict,
                              systems: Optional[dict] = None) -> List[int]:
    """
    Номера контрольных точек, от которых зависит система (и её дети)

    Ими игра управляет из кода - цвет килстрика на CP 9, положение оружия на
    CP 1 и так далее. В превью такие точки надо выставить руками, а понять,
    какие именно, можно только вычитав их из модулей эффекта
    """
    refs, own = _control_point_refs(sys_json, systems)
    return sorted({cp for cp, _fn, _attr in refs} - own)


#: Роли точки в порядке важности: если точку читают несколько модулей,
#: подпись берётся у самого понятного
CONTROL_POINT_ROLES = ('origin', 'path_end', 'follow', 'pull', 'distance', 'remap')


def _control_point_role(fn: str, attr: str) -> str:
    """Зачем модуль читает точку - по его функции и атрибуту. Пусто - по
    модулю не сказать, и придумывать смысл не надо"""
    fn, attr = fn.lower(), attr.lower()
    if "end control point" in attr:
        return "path_end"              # конец пути: трассер, луч
    if "distance" in fn:
        return "distance"
    if "remap" in fn:
        return "remap"                 # значение из кода: цвет килстрика
    if "lock to control point" in fn or "follow" in fn:
        return "follow"
    if any(w in fn for w in ("pull", "attract", "twist", "towards")):
        return "pull"
    if fn.startswith("position") or "emit" in fn:
        return "origin"
    return ""


def control_point_roles(sys_json: dict,
                        systems: Optional[dict] = None) -> Dict[int, str]:
    """{номер нужной точки: роль из CONTROL_POINT_ROLES} - подпись к номеру
    в превью. Точки без понятной роли сюда не попадают"""
    refs, own = _control_point_refs(sys_json, systems)
    best: Dict[int, int] = {}
    for cp, fn, attr in refs:
        role = _control_point_role(fn, attr)
        if cp in own or not role:
            continue
        rank = CONTROL_POINT_ROLES.index(role)
        if rank < best.get(cp, len(CONTROL_POINT_ROLES)):
            best[cp] = rank
    return {cp: CONTROL_POINT_ROLES[rank] for cp, rank in sorted(best.items())}


def _self_set_control_points(mod: dict) -> set:
    """Номера точек, которые модуль выставляет сам (см. движок:
    set child control points / set control point positions)"""
    attrs = mod.get("attrs") or {}

    def num(key: str, default: int) -> int:
        v = (attrs.get(key) or {}).get("v", default)
        return v if isinstance(v, int) and not isinstance(v, bool) else default

    fn = (mod.get("functionName") or "").lower()
    if fn == "set child control points from particle positions":
        first = num("first control point to set", 0)
        return set(range(first, first + num("# of control points to set", 1)))
    if fn == "set control point positions":
        return {n for n in (num(f"{o} control point number", -1)
                            for o in ("first", "second", "third", "fourth"))
                if n >= 0}
    return set()


def system_hierarchy(systems: dict, order: Optional[List[str]] = None) -> list:
    """Иерархия систем: [(имя, [(ребёнок, [...]), ...]), ...]

    Корень - система, которую никто, кроме неё самой, не называет своим
    ребёнком. В большом файле корней в разы меньше, чем определений: в
    summer2024_unusuals.pcf из 611 систем корней 52, остальные - служебные
    держатели и спавнеры

    Один ребёнок может висеть сразу у нескольких родителей (в PCF это ссылка
    по имени, а не владение) - тогда он появится под каждым из них, так оно и
    есть на самом деле. Циклы обрываются по пути от корня

    Из списка ничего не пропадает: система, до которой не дотянуться ни от
    одного корня (взаимный цикл), добавляется вершиной сама

    order задаёт порядок вершин, имена не из systems игнорируются
    """
    names = list(order) if order is not None else list(systems)
    names = [n for n in names if n in systems]

    referenced = set()
    for name, s in systems.items():
        for c in s.get("children") or []:
            child = c.get("childName")
            if child != name:          # сам себе родителем не считается
                referenced.add(child)

    def subtree(name: str, path: frozenset) -> tuple:
        kids = []
        for c in systems.get(name, {}).get("children") or []:
            child = c.get("childName")
            if child in systems and child not in path:
                kids.append(subtree(child, path | {child}))
        return (name, kids)

    tree = [subtree(n, frozenset({n})) for n in names if n not in referenced]

    # Взаимный цикл без входа снаружи: иначе такие системы исчезли бы из UI
    shown = set(flatten_hierarchy(tree))
    for n in names:
        if n not in shown:
            node = subtree(n, frozenset({n}))
            tree.append(node)
            shown.update(flatten_hierarchy([node]))
    return tree
