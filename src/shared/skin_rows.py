"""Таблица скинов модели ($texturegroup): строки, столбцы, стили и их пары

Сырые строки ходили по коду списком, и каждое место само искало столбец
материала и строку стиля - со своими ошибками регистра и границ. Вопросы к
таблице задаются здесь: превью, модель текстур и сборка отвечают одинаково"""

from typing import List, Optional, Sequence, Tuple

from src.shared.game_paths import game_path
from src.shared.team_names import team_form


def find_name(names: Sequence[str], name: str) -> int:
    """Индекс материала в списке имён: точно без учёта регистра, иначе по
    хвосту ПУТИ - имена в SMD и в $texturegroup иногда расходятся префиксом
    папки (`models/x/c_hat` и `c_hat`). Только по границе `/`: голый хвост
    сводил бы `lens` с `c_rocketlauncher_lens`. -1 - не нашёлся"""
    low = game_path(name).strip('/')
    if not low:
        return -1
    lows = [game_path(n) for n in names]
    if low in lows:
        return lows.index(low)
    return next((i for i, n in enumerate(lows)
                 if n and (low.endswith('/' + n) or n.endswith('/' + low))), -1)


def is_team_row_pair(red_row: Sequence[str], blu_row: Sequence[str]) -> bool:
    """
    Вторая строка - синяя команда первой, а не стиль или вариант

    Команда в Source меняет материалы ПОКОЛОНОЧНО и не обязательно все:
    столбец либо остаётся тем же (нейтральная деталь), либо заменяется на
    свою синюю пару. Достаточно одного изменённого столбца - но любая
    ПОСТОРОННЯЯ разница означает, что это стиль (bloody/clean), а не команда

        { c_proto_medigun_glass  c_proto_medigun       c_proto_medigun_blue }
        { c_proto_medigun_glass  c_proto_medigun_blue  c_proto_medigun_blue }

    Проверка только по col0 признала бы Quick-Fix некомандным: стекло у него
    общее, а меняется второй столбец
    """
    width = min(len(red_row or []), len(blu_row or []))
    changed = False
    for i in range(width):
        red, blu = (red_row[i] or '').lower(), (blu_row[i] or '').lower()
        if red == blu:
            continue
        red_stem, red_is_blue = team_form(red)
        blu_stem, blu_is_blue = team_form(blu)
        if blu_is_blue and not red_is_blue and red_stem == blu_stem:
            changed = True
            continue
        return False
    return changed


def blu_twin(rows: Sequence[Sequence[str]], style: int) -> int:
    """Синяя строка стиля или 0

    У Горящих рукавиц ускорения синий огонь - своя строка сразу за красной
    (`c_boxing_gloves_flames` -> `_flames_blue`), а у Баккары и крови катаны
    синяя строка та же, что красная, и пары нет. Правило то же, что у
    команды базовых строк (is_team_row_pair), по всем столбцам
    """
    if not 0 < style < len(rows) - 1:
        return 0
    return style + 1 if is_team_row_pair(rows[style], rows[style + 1]) else 0


class SkinTable:
    """Строки `$texturegroup`: [0] - база (материалы мешей), дальше скины"""

    def __init__(self, rows: Optional[Sequence[Sequence[str]]] = None):
        self.rows: List[List[str]] = [[str(n) for n in r] for r in rows or ()]
        self._head = [n.lower() for n in self.rows[0]] if self.rows else []

    def __bool__(self) -> bool:
        return bool(self.rows)

    def __len__(self) -> int:
        return len(self.rows)

    def col_of(self, base: str) -> int:
        """Столбец материала меша (find_name), -1 - не в таблице"""
        return find_name(self._head, base)

    def name_at(self, row: int, col: int) -> Optional[str]:
        """Материал ячейки или None за границами"""
        if 0 <= row < len(self.rows) and 0 <= col < len(self.rows[row]):
            return self.rows[row][col]
        return None

    def changes(self, row: int, base: str) -> bool:
        """Меняет ли строка материал меша `base` (стиль его переопределяет)"""
        col = self.col_of(base)
        name = self.name_at(row, col)
        return bool(row) and name is not None and name.lower() != self._head[col]

    def cells(self, material: str) -> List[Tuple[int, int]]:
        """(строка, столбец), где материал ЗАМЕНЯЕТ меш базы. Строка, где
        столбец остался прежним (копия базы, общая деталь), сюда не входит"""
        low = (material or '').lower()
        return [(r, c) for r in range(1, len(self.rows))
                for c, name in enumerate(self.rows[r])
                if c < len(self._head) and name.lower() == low and self._head[c] != low]

    def style_rows(self, style: int) -> List[int]:
        """Строки, которые и есть этот стиль: у Australium их две (RED и
        BLU одинаковые), у Bloody гильотины одна"""
        if not 0 < style < len(self.rows):
            return [style] if style else []
        return [r for r, row in enumerate(self.rows) if r and row == self.rows[style]]

    def is_team_row(self, row: int) -> bool:
        """Командная строка базы (синяя у большинства моделей), а не стиль"""
        return 0 < row < len(self.rows) and is_team_row_pair(self.rows[0], self.rows[row])

    def blu_row(self, red: int) -> int:
        """Синяя строка стиля или 0, если синяя у стиля та же, что красная"""
        return blu_twin(self.rows, red) if red else 0

    def red_row(self, row: int) -> int:
        """Красная строка: у синей строки стиля - его красная, иначе сама"""
        return row - 1 if row > 1 and self.blu_row(row - 1) == row else row

    def team_differs(self, red: int, col: int) -> bool:
        """Отличается ли у стиля `red` синий материал столбца от красного"""
        blue = self.blu_row(red)
        names = (self.name_at(red, col), self.name_at(blue, col)) if blue else (None, None)
        return None not in names and names[0] != names[1]

    def gold_row(self) -> int:
        """Первая строка Australium (0 - нет): тот же скин с материалом `_gold`"""
        base = self._head[0] if self._head else ''
        return next((r for r, row in enumerate(self.rows)
                     if row and row[0].lower() != base and row[0].lower().endswith('_gold')), 0)
