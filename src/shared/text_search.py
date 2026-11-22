"""Сравнение строк для поиска: без знаков, регистра и различия «ё/е»

И поиск с опечатками. Правило как у Algolia: в слове до трёх букв опечаток не
бывает, с четырёх прощается одна, с восьми - две. Опечатка ищется в НАЧАЛЕ
слов словаря, а не где угодно в тексте: иначе «fire» находило бы «affirm».
Точные совпадения всегда выше: нечёткое - запасной путь, а не замена
"""

import re
from typing import Dict, Iterable, List, Optional, Tuple

_YO = str.maketrans('ё', 'е')
#: Латиница, цифры и кириллица а-я (кодами: проверка переводов иначе
#: принимает диапазон за надпись интерфейса)
_WORD = re.compile(r'[0-9a-z\u0430-\u044f]+')


def plain(text: str) -> str:
    """Только буквы и цифры, в нижнем регистре, «ё» как «е»"""
    return (re.sub(r'[^0-9a-zA-Zа-яёА-ЯЁ]+', '', text or '')
            .lower().translate(_YO))


def words_of(text: str) -> List[str]:
    """Слова текста: «superrare_burning1» -> superrare, burning1"""
    return _WORD.findall((text or '').lower().translate(_YO))


def typo_budget(word: str) -> int:
    """Сколько опечаток прощать слову запроса"""
    return 0 if len(word) < 4 else 1 if len(word) < 8 else 2


def prefix_typos(query: str, word: str, limit: int) -> int:
    """Сколько правок отделяют запрос от лучшего начала слова

    Расстояние Дамерау-Левенштейна (перестановка соседних букв - одна
    правка: «fedroa»), хвост слова бесплатный: «fedra» против «fedora»
    стоит одну правку, как и против «fedoras». Больше limit - limit + 1
    """
    n = len(query)
    m = min(len(word), n + limit)
    before: List[int] = []
    prev = list(range(m + 1))
    for i in range(1, n + 1):
        cur = [i] + [0] * m
        q = query[i - 1]
        for j in range(1, m + 1):
            w = word[j - 1]
            best = min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (q != w))
            if i > 1 and j > 1 and q == word[j - 2] and query[i - 2] == w:
                best = min(best, before[j - 2] + 1)
            cur[j] = best
        if min(cur) > limit:
            return limit + 1
        before, prev = prev, cur
    return min(prev)


class TypoIndex:
    """Словарь каталога: какие его слова считать словом запроса с опечаткой

    Строится один раз на каталог. Ответы на слова запроса запоминаются:
    поиск идёт на каждую букву, а слово «fedra» успевают спросить трижды
    """

    _MEMO = 256

    def __init__(self, texts: Iterable[str]) -> None:
        vocab = {w for t in texts for w in words_of(t) if len(w) >= 3}
        self._vocab: Tuple[str, ...] = tuple(sorted(vocab))
        self._near: Dict[str, Tuple[str, ...]] = {}

    def near(self, query: str) -> Tuple[str, ...]:
        """Слова словаря, начало которых - query с опечатками в пределах
        правила. Само query сюда не входит: его ищут как есть"""
        budget = typo_budget(query)
        if not budget:
            return ()
        if query not in self._near:
            if len(self._near) >= self._MEMO:
                self._near.clear()
            shortest = len(query) - budget
            self._near[query] = tuple(
                w for w in self._vocab
                if len(w) >= shortest and not w.startswith(query)
                and prefix_typos(query, w, budget) <= budget)
        return self._near[query]


def find(words: List[str], text: str, index: Optional[TypoIndex]) -> Optional[int]:
    """Нашлись ли все слова запроса в тексте

    None - нет. Иначе - сколько слов нашлось только с опечаткой: 0 значит
    всё точно, и такую строку ставят выше. Текст - тот, по которому каталог
    искал и раньше (подстрокой), опечатки сверяются со словами словаря
    """
    typos = 0
    for w in words:
        if w in text:
            continue
        if index is not None and any(n in text for n in index.near(w)):
            typos += 1
            continue
        return None
    return typos
