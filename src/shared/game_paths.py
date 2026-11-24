"""Пути файлов игры как ключи сравнения: одно правило на весь код

Движок не различает регистр и сорт слэшей, а `$baseTexture` пишется от
`materials/` без расширения. Копии этого правила расходились: одни отрезали
только `.vtf`, и у праздничного Правосудия с `..._xmas.psd` в VMT игровую
текстуру не узнавали"""


def game_path(path) -> str:
    """Путь файла игры для сравнения: прямые слэши, нижний регистр"""
    return str(path or '').replace('\\', '/').strip().lower()


def texture_key(path) -> str:
    """Текстура так, как её читает движок: от materials/, без расширения

    В VMT встречается ИСХОДНОЕ расширение: у праздничного Правосудия и
    Уберпилы Valve оставила `$baseTexture "..._xmas.psd"`. Движок читает такой
    путь без расширения, и мы тоже - иначе текстуры у них нет
    """
    key = game_path(path).strip('/')
    if key.startswith('materials/'):
        key = key[len('materials/'):]
    stem, dot, ext = key.rpartition('.')
    return stem if dot and '/' not in ext else key
