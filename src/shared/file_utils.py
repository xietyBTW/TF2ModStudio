"""
Утилиты для работы с файлами
"""

import os
import shutil
import threading
from collections import deque
from pathlib import Path
from typing import Optional
from .exceptions import RequiredFileMissingError


def existing_file(path: Optional[str]) -> Optional[str]:
    """Путь, если файл на месте, иначе None"""
    return path if path and os.path.isfile(path) else None


def ensure_directory_exists(dir_path: str | Path) -> Path:
    """
    Создает директорию если не существует

    Args:
        dir_path: Путь к директории

    Returns:
        Path объект директории
    """
    path = Path(dir_path)
    path.mkdir(parents=True, exist_ok=True)
    return path


def safe_remove(path: str | Path, is_dir: bool = False) -> bool:
    """
    Безопасно удаляет файл или директорию

    Args:
        path: Путь к файлу/директории
        is_dir: True если это директория

    Returns:
        True если удаление успешно, False если ошибка
    """
    try:
        path_obj = Path(path)
        if not path_obj.exists():
            return True

        if is_dir:
            shutil.rmtree(path_obj)
        else:
            path_obj.unlink()
        return True
    except Exception:
        return False


def folder_size(folder: str | Path) -> int:
    """Сколько байт в папке со всеми вложенными. Нет папки - ноль"""
    total = 0
    for root, _dirs, files in os.walk(folder):
        for name in files:
            try:
                total += os.path.getsize(os.path.join(root, name))
            except OSError:                  # файл ушёл между обходом и stat
                pass
    return total


def copy_file_safe(source: str | Path, destination: str | Path) -> Path:
    """
    Безопасно копирует файл, создавая директорию назначения если нужно

    Args:
        source: Путь к исходному файлу
        destination: Путь к файлу назначения

    Returns:
        Path к скопированному файлу

    Raises:
        RequiredFileMissingError: Если исходный файл не существует
    """
    source_path = Path(source)
    if not source_path.is_file():
        raise RequiredFileMissingError(str(source_path))
    dest_path = Path(destination)

    # Создаем директорию назначения если нужно
    dest_path.parent.mkdir(parents=True, exist_ok=True)

    shutil.copy2(source_path, dest_path)
    return dest_path


# Префиксы наших временных файлов/папок в системной temp (3D-превью, VTF-превью,
# декомпиляция и т.п.). Файлы нужны UI и после завершения воркеров, поэтому
# удаляются не сразу, а отложенно - cleanup_stale_temp_artifacts при старте
_TEMP_ARTIFACT_PREFIXES = (
    "tf2sg_",
    "tf2_crithit_", "tf2_smd_preview_", "tf2_3d_", "tf2_3ddrop_",
    "tf2_deatheff_", "tf2_model_tex_", "tf2_vtf_",
    "tf2_sky_",   # грани скайбокса: нарезка панорамы + стоковые превью
    "tf2_mesh_",  # импорт OBJ/GLB: SMD с подгонкой и вытащенные текстуры
    "tf2_scene_",  # текстуры особых сцен (смерть, крит): VTF -> PNG
)


def cleanup_stale_temp_artifacts(max_age_hours: float = 24.0,
                                 temp_dir: Optional[Path] = None) -> int:
    """
    Удаляет из системной temp-папки устаревшие артефакты приложения
    (папки/файлы с нашими префиксами старше max_age_hours)

    Без этого temp-папки превью (tf2sg_3d_* и др.) копились бы бесконечно.
    Порог по возрасту защищает файлы текущего и параллельного запусков. Ошибки удаления (файл занят) молча пропускаются

    Returns:
        Количество удалённых записей
    """
    import tempfile
    import time

    root = Path(temp_dir) if temp_dir else Path(tempfile.gettempdir())
    cutoff = time.time() - max_age_hours * 3600
    removed = 0
    try:
        entries = list(os.scandir(root))
    except OSError:
        return 0
    for entry in entries:
        if not entry.name.startswith(_TEMP_ARTIFACT_PREFIXES):
            continue
        try:
            if entry.stat().st_mtime >= cutoff:
                continue
            if entry.is_dir():
                shutil.rmtree(entry.path, ignore_errors=True)
            else:
                os.unlink(entry.path)
            removed += 1
        except OSError:
            continue
    return removed


#: Сколько последних папок превью одного вида держать: старше - их файлы уже
#: не нужны ни сеансу (состояние переписывается на новую папку), ни кадру
PREVIEW_DIRS_KEPT = 5
_preview_dirs: dict = {}
_preview_lock = threading.Lock()


def make_preview_dir(prefix: str, keep: int = PREVIEW_DIRS_KEPT) -> str:
    """
    Папка в %TEMP% под одно превью; самые старые этого же вида удаляются

    Без этого за сеанс каждая смена модели оставляла папку на 2-6 МБ до
    следующего запуска. Удаляются только папки ЭТОГО процесса: по маске
    dev-сервер стирал бы файлы открытого рядом приложения
    """
    import tempfile

    path = tempfile.mkdtemp(prefix=prefix)
    with _preview_lock:
        made = _preview_dirs.setdefault(prefix, deque())
        made.append(path)
        stale = [made.popleft() for _ in range(max(0, len(made) - keep))]
    for old in stale:
        shutil.rmtree(old, ignore_errors=True)
    return path


def get_temp_file_path(prefix: str = "temp", suffix: str = ".tmp") -> Path:
    """
    Генерирует путь к временному файлу (безопасная замена tempfile.mktemp)

    Args:
        prefix: Префикс имени файла
        suffix: Суффикс (расширение)

    Returns:
        Path к временному файлу
    """
    import tempfile

    fd, path = tempfile.mkstemp(prefix=prefix, suffix=suffix)
    os.close(fd)
    return Path(path)
