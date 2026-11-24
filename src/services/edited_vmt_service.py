"""
Правки VMT открытого предмета: доступ по ключу материала

Сами правки живут в работе предмета (PreviewSession.vmt,
src/domain/preview/vmt_edits.py). Здесь - прежний набор вызовов, на который
опираются редактор VMT, части и сборка: сборке по-прежнему нужен путь к
файлу, и она получает копию правки во временной папке

Сборка идёт фоном, а человек тем временем может открыть другой предмет:
её поток работает со снимком правок (`use`), а не с открытым предметом

Раньше правки лежали общей папкой по имени материала (tools/edited_vmt) и
подставлялись при любом открытии предмета. Такие файлы переезжают в предмет,
который первым откроется с этим материалом (`adopt_legacy`)
"""

import hashlib
import os
import tempfile
import threading
from contextlib import contextmanager
from typing import Callable, Dict, Iterable, Optional

from src.domain.preview.vmt_edits import VmtEdits
from src.shared.constants import DirectoryPaths
from src.shared.logging_config import get_logger

logger = get_logger(__name__)


class EditedVMTService:
    """Правки VMT по ключу: имя материала (`c_scattergun`) или ключ
    материала мода (`mod_key`). Рядом - игровой оригинал первой правки"""

    #: Старая общая папка правок - только для переезда (`adopt_legacy`)
    EDITED_VMT_DIR = str(DirectoryPaths.EDITED_VMT_DIR)

    #: Откуда брать правки открытого предмета (ставит сеанс, `bind`)
    _live: Optional[Callable[[], VmtEdits]] = None
    #: Снимок правок для потока сборки (`use`)
    _local = threading.local()

    @staticmethod
    def mod_key(mod_path: str, material: str) -> str:
        """Ключ правки материала мода из VPK. У мода свой VMT: правка того
        же материала игры (тот же c_shogun_kunai) в него попадать не должна,
        как и правка одного мода в другой"""
        digest = hashlib.sha1(os.path.normcase(os.path.abspath(mod_path))
                              .encode('utf-8')).hexdigest()[:8]
        return f"vpkmod_{digest}_{material}"

    # Откуда правки

    @classmethod
    def bind(cls, live: Callable[[], VmtEdits]) -> None:
        """Правки открытого предмета: сеанс отдаёт их при каждом обращении"""
        cls._live = live

    @classmethod
    @contextmanager
    def use(cls, edits: Optional[VmtEdits]):
        """Поток сборки работает со снимком правок, а не с открытым предметом"""
        was = getattr(cls._local, 'edits', None)
        cls._local.edits = edits
        try:
            yield
        finally:
            cls._local.edits = was

    @classmethod
    def snapshot(cls) -> VmtEdits:
        """Снимок правок открытого предмета - для сборки"""
        return cls._edits().copy()

    @classmethod
    def _edits(cls) -> VmtEdits:
        pinned = getattr(cls._local, 'edits', None)
        if pinned is not None:
            return pinned
        live = cls._live() if cls._live else None
        return live if live is not None else VmtEdits()

    # Правка

    @classmethod
    def _key(cls, edit_key: str) -> Optional[str]:
        """Ключ, под которым лежит правка. Сборка спрашивает по имени в модели
        (`material_001`), а правка лежит под именем карточки (`Material.001`
        из Blender): studiomdl собирает их в один материал (part_materials)"""
        texts = cls._edits().texts
        if edit_key in texts:
            return edit_key
        # Файлами правки находились без учёта регистра (Windows), и сборка
        # спрашивает их то именем карточки, то именем из модели
        same = next((k for k in texts if k.lower() == str(edit_key or '').lower()), None)
        if same is not None:
            return same
        from src.services.part_materials import model_name
        if edit_key and edit_key == model_name(edit_key):
            return next((k for k in texts if model_name(k) == edit_key), None)
        return None

    @classmethod
    def has_edited_vmt(cls, edit_key: str) -> bool:
        return cls._key(edit_key) is not None

    @classmethod
    def get_text(cls, edit_key: str) -> Optional[str]:
        """Текст правки или None"""
        key = cls._key(edit_key)
        return cls._edits().texts[key] if key is not None else None

    @classmethod
    def get_edited_vmt(cls, edit_key: str) -> Optional[str]:
        """Путь к файлу с правкой (копия во временной папке) или None.
        Файл назван по содержимому: прошлую копию никто не перепутает"""
        text = cls.get_text(edit_key)
        if text is None:
            return None
        digest = hashlib.sha1(text.encode('utf-8')).hexdigest()[:12]
        folder = os.path.join(tempfile.gettempdir(), 'tf2sg_vmt_edits', digest)
        os.makedirs(folder, exist_ok=True)
        path = os.path.join(folder, f"{edit_key}.vmt")
        if not os.path.isfile(path):
            # Через временный: оборванная запись иначе осталась бы «готовой»
            # копией, которой верит каждая следующая сборка
            tmp = f"{path}.{threading.get_ident()}.tmp"
            with open(tmp, 'w', encoding='utf-8') as f:
                f.write(text)
            os.replace(tmp, path)
        return path

    @classmethod
    def save_edited_vmt(cls, edit_key: str, vmt_content: str) -> None:
        """Под уже известным ключом, если он отличается только регистром"""
        cls._edits().texts[cls._key(edit_key) or edit_key] = vmt_content

    @classmethod
    def delete_edited_vmt(cls, edit_key: str) -> bool:
        """Снимает правку вместе с оригиналом. False - правки не было"""
        edits = cls._edits()
        key = cls._key(edit_key) or edit_key
        edits.origs.pop(cls._orig_key(key), None)
        return edits.texts.pop(key, None) is not None

    # Игровой оригинал первой правки («Вернуть игровой»)

    @classmethod
    def _orig_key(cls, edit_key: str) -> str:
        origs = cls._edits().origs
        return next((k for k in origs if k.lower() == str(edit_key or '').lower()), edit_key)

    @classmethod
    def has_original_backup(cls, edit_key: str) -> bool:
        return cls._orig_key(edit_key) in cls._edits().origs

    @classmethod
    def save_original_backup(cls, edit_key: str, content: str) -> None:
        cls._edits().origs[cls._orig_key(edit_key)] = content

    @classmethod
    def read_original_backup(cls, edit_key: str) -> Optional[str]:
        return cls._edits().origs.get(cls._orig_key(edit_key))

    # Переезд старых общих правок

    @classmethod
    def adopt_legacy(cls, keys: Iterable[str], remove: bool = True) -> Dict[str, str]:
        """
        Старые правки из общей папки - в открытый предмет, по его материалам

        Каждый файл переезжает один раз: дальше правка живёт в работе этого
        предмета, а у других она не всплывёт. `remove=False` - файл остаётся
        (работа не запишется на диск, и правка иначе пропала бы). Возвращает
        {ключ: текст}
        """
        moved: Dict[str, str] = {}
        edits = cls._edits()
        for key in dict.fromkeys(k for k in keys if k):
            vmt = os.path.join(cls.EDITED_VMT_DIR, f"{key}.vmt")
            orig = os.path.join(cls.EDITED_VMT_DIR, f"{key}.orig")
            if key in edits.texts or not os.path.isfile(vmt):
                continue
            try:
                with open(vmt, encoding='utf-8', errors='replace') as f:
                    edits.texts[key] = moved[key] = f.read()
                if os.path.isfile(orig):
                    with open(orig, encoding='utf-8', errors='replace') as f:
                        edits.origs[key] = f.read()
                if remove:
                    os.remove(vmt)
                    if os.path.isfile(orig):
                        os.remove(orig)
            except OSError as exc:
                logger.warning(f"[vmt] старая правка {key} не перенесена: {exc}")
                continue
            logger.info(f"[vmt] старая общая правка {key} перенесена в работу предмета")
        return moved
