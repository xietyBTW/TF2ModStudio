import os
import shutil
from pathlib import Path
from typing import Callable, Optional, Tuple, List, Dict, Any

from src.data.translations import TRANSLATIONS
from src.data.weapons import WEAPON_MDL_PATHS
from src.services.build_context import BuildContext
from src.data.item_kinds import kind_of
from src.services.model_locator import first_existing, mdl_candidates, not_found_error
from src.shared.game_paths import game_path
from src.services import model_decompile_service as mds
from src.services.tf2_paths import TF2Paths, build_hat_mdl_candidates
from src.services.tf2_vpk_extract_service import TF2VPKExtractService
from src.shared.file_utils import ensure_directory_exists
from src.shared.logging_config import get_logger

logger = get_logger(__name__)


class ExtractModelService:
    @staticmethod
    def _next_available_dir(base_dir: Path, base_name: str) -> Path:
        for i in range(1, 1000000):
            candidate = base_dir / f"{base_name}_{i}"
            if not candidate.exists():
                return candidate
        raise RuntimeError("Не удалось подобрать уникальное имя папки экспорта")

    @staticmethod
    def _next_available_file(base_dir: Path, file_name: str) -> Path:
        candidate = base_dir / file_name
        if not candidate.exists():
            return candidate

        stem = candidate.stem
        suffix = candidate.suffix
        for i in range(1, 1000000):
            cand = base_dir / f"{stem}_{i}{suffix}"
            if not cand.exists():
                return cand
        raise RuntimeError("Не удалось подобрать уникальное имя файла экспорта")

    @staticmethod
    def cleanup_temp_dir(temp_dir: str) -> None:
        try:
            if temp_dir and os.path.exists(temp_dir):
                shutil.rmtree(temp_dir, ignore_errors=True)
        except Exception:
            pass

    @staticmethod
    def generate_uv_template(
        decompile_dir: str,
        weapon_key: str,
        image_size: Tuple[int, int],
        export_folder: str = "export",
    ) -> Tuple[bool, str, List[str]]:
        """
        Генерирует PNG c UV-разметкой из уже декомпилированной модели
        (без полной сборки мода)

        Файлов бывает несколько: у каждого материала своя текстура и своя
        развёртка, а на одной картинке они ложатся друг на друга

        Returns:
            (успех, первый файл или причина отказа, все файлы)
        """
        from src.services import smd_service
        from src.services.uv_layout_service import UVLayoutService

        smd_path = smd_service.find_reference_smd(str(decompile_dir), weapon_key)
        if not smd_path or not os.path.exists(smd_path):
            logger.warning(f"UV-шаблон: не найден reference SMD для {weapon_key} в {decompile_dir}")
            return False, "no_smd", []

        # weapon_key для персонажей/шапок может быть полным mdl-путём - берём
        # безопасное имя файла из его basename
        safe_name = Path(str(weapon_key).replace("\\", "/")).stem or "model"
        out_path = ExtractModelService._next_available_file(
            Path(export_folder), f"{safe_name}_uv_layout.png"
        )
        ensure_directory_exists(out_path.parent)
        written = UVLayoutService.generate_uv_layout_from_smd(
            smd_path, str(out_path), image_size)
        if written:
            logger.info(f"UV-шаблон сохранён: {len(written)} файл(ов), {written[0]}")
            return True, written[0], written
        return False, "render_failed", []

    @staticmethod
    def prepare_decompiled_model_files_with_progress(
        tf2_root_dir: str,
        mode: str,
        weapon_key: str,
        language: str = "en",
        progress_callback: Optional[Callable[[int, str], None]] = None,
        cancel_callback: Optional[Callable[[], bool]] = None,
        hat_class_models: Optional[Dict[str, str]] = None,
    ) -> Tuple[bool, str, bool, Optional[Dict[str, Any]]]:
        t = TRANSLATIONS.get(language, TRANSLATIONS["en"])

        def emit_progress(pct: int, status_key: str, fallback: str) -> None:
            if progress_callback:
                progress_callback(pct, t.get(status_key, fallback))

        def is_cancelled() -> bool:
            return bool(cancel_callback and cancel_callback())

        ctx: Optional[BuildContext] = None
        try:
            emit_progress(5, "extract_model_init", "Инициализация извлечения модели...")
            if is_cancelled():
                return False, t.get("extract_model_cancelled", "Извлечение отменено пользователем"), True, None

            if not tf2_root_dir:
                return False, t.get("tf2_path_not_specified", "TF2 path not specified in settings"), False, None

            kind = kind_of(mode)
            # У шапки, тела и маски ключ - сразу путь MDL ("models/player/spy.mdl")
            by_path = kind.model_by_path or weapon_key.lower().endswith(".mdl")

            if not by_path and weapon_key not in WEAPON_MDL_PATHS:
                return (
                    False,
                    t.get("error_weapon_not_found", "Weapon not found").format(weapon_key=weapon_key),
                    False,
                    None,
                )

            crowbar_exists, crowbar_error = TF2Paths.check_crowbar()
            if not crowbar_exists:
                return False, crowbar_error or "Crowbar CLI missing", False, None

            emit_progress(15, "extract_model_checking", "Проверка файлов игры...")
            _, tf2_misc_vpk, _ = TF2Paths.resolve(tf2_root_dir)

            # Мультиклассовая шапка: извлекаем и декомпилируем модель КАЖДОГО класса
            # в свою подпапку decompile_dir/<class>/ - чтобы в экспорте были все
            # классы, а не только первый найденный
            if kind.class_models and hat_class_models and len(hat_class_models) > 1:
                return ExtractModelService._prepare_multiclass_hat(
                    tf2_misc_vpk, hat_class_models, weapon_key, mode, t,
                    emit_progress, is_cancelled,
                )

            paths_to_try = mdl_candidates(mode, weapon_key, tf2_root_dir)
            def step(done: int, total: int) -> None:
                if progress_callback:
                    progress_callback(15 + int(done / max(1, total) * 20),
                                      t.get("extract_model_searching", "Поиск модели..."))

            found_mdl_path, last_error = first_existing(
                tf2_misc_vpk, paths_to_try, is_cancelled, step)
            if is_cancelled():
                return False, t.get("extract_model_cancelled", "Извлечение отменено пользователем"), True, None
            if not found_mdl_path:
                return False, not_found_error(t, paths_to_try, tf2_misc_vpk, last_error), False, None

            emit_progress(40, "extract_model_extracting", "Извлечение модели...")
            if is_cancelled():
                return False, t.get("extract_model_cancelled", "Извлечение отменено пользователем"), True, None

            ctx = BuildContext.create(f"model_export_{mode}", weapon_key, debug_mode=False)

            qc = mds.decompile_into(
                weapon_key, tf2_misc_vpk, [found_mdl_path], str(ctx.decompile_dir),
                cancelled=is_cancelled,
                on_progress=lambda stage: emit_progress(
                    70, "extract_model_decompiling", "Декомпиляция модели...")
                    if stage is mds.Stage.DECOMPILING else None,
            )
            if is_cancelled():
                ExtractModelService.cleanup_temp_dir(str(ctx.temp_dir))
                return False, t.get("extract_model_cancelled", "Извлечение отменено пользователем"), True, None
            if not qc:
                ExtractModelService.cleanup_temp_dir(str(ctx.temp_dir))
                return (
                    False,
                    t.get("error_mdl_not_extracted", "MDL not extracted").format(path=found_mdl_path),
                    False,
                    None,
                )

            emit_progress(95, "extract_model_completed", "Извлечение завершено")

            decompile_dir = Path(ctx.decompile_dir)
            files: List[str] = []
            for p in decompile_dir.rglob("*"):
                if p.is_file():
                    files.append(p.relative_to(decompile_dir).as_posix())
            files.sort()

            data = {
                "temp_dir": str(ctx.temp_dir),
                "decompile_dir": str(decompile_dir),
                "files": files,
            }
            return True, t.get("extract_model_completed", "Извлечение завершено"), False, data
        except Exception as e:
            logger.error(f"Ошибка при подготовке файлов модели: {e}", exc_info=True)
            if ctx:
                ExtractModelService.cleanup_temp_dir(str(ctx.temp_dir))
            return False, str(e), False, None

    @staticmethod
    def _resolve_existing_mdl(tf2_misc_vpk: str, mdl_rel: str) -> Optional[str]:
        """Возвращает путь MDL, который реально есть в VPK (прямой или вариант)"""
        norm = game_path(mdl_rel)
        return first_existing(tf2_misc_vpk, [norm] + build_hat_mdl_candidates(norm))[0] if norm else None

    @staticmethod
    def _prepare_multiclass_hat(
        tf2_misc_vpk: str,
        hat_class_models: Dict[str, str],
        weapon_key: str,
        mode: str,
        t: dict,
        emit_progress,
        is_cancelled,
    ) -> Tuple[bool, str, bool, Optional[Dict[str, Any]]]:
        """
        Извлекает + декомпилирует модель каждого класса в decompile_dir/<class>/

        Ошибка одного класса не валит весь экспорт - он просто пропускается
        """
        ctx = BuildContext.create(f"model_export_{mode}", weapon_key, debug_mode=False)
        decompile_root = Path(ctx.decompile_dir)
        files: List[str] = []
        done_classes: List[str] = []

        classes = list(hat_class_models.items())
        for idx, (cls, mdl_rel) in enumerate(classes):
            if is_cancelled():
                ExtractModelService.cleanup_temp_dir(str(ctx.temp_dir))
                return False, t.get("extract_model_cancelled", "Извлечение отменено пользователем"), True, None
            pct = 20 + int((idx) / max(1, len(classes)) * 70)
            emit_progress(pct, "extract_model_extracting", f"Извлечение модели: {cls}...")

            found = ExtractModelService._resolve_existing_mdl(tf2_misc_vpk, mdl_rel)
            if not found:
                logger.warning(f"[EXPORT MULTI] MDL класса {cls} не найден в игре: {mdl_rel}")
                continue
            try:
                # Ключ как у сборки мультиклассовой шапки: одна запись кэша на модель
                if mds.decompile_into(Path(found).stem, tf2_misc_vpk, [found],
                                      str(decompile_root / cls), cancelled=is_cancelled):
                    done_classes.append(cls)
            except Exception as exc:
                logger.warning(f"[EXPORT MULTI] {cls}: ошибка извлечения/декомпиляции: {exc}",
                               exc_info=True)
                continue

        if not done_classes:
            ExtractModelService.cleanup_temp_dir(str(ctx.temp_dir))
            return False, t.get("error_mdl_not_found", "MDL not found"), False, None

        for p in decompile_root.rglob("*"):
            if p.is_file():
                files.append(p.relative_to(decompile_root).as_posix())
        files.sort()

        emit_progress(95, "extract_model_completed", "Извлечение завершено")
        logger.info(f"[EXPORT MULTI] декомпилированы классы: {done_classes}")
        data = {
            "temp_dir": str(ctx.temp_dir),
            "decompile_dir": str(decompile_root),
            "files": files,
        }
        return True, t.get("extract_model_completed", "Извлечение завершено"), False, data

    @staticmethod
    def default_export_selection(file_names: List[str]) -> List[str]:
        """
        Что отметить по умолчанию в списке подготовленных файлов

        Обычно нужен один файл - reference-SMD: это сама геометрия, остальное
        (физика, LOD, анимации) человек берёт осознанно. Правило общее для окна
        и для веб-страницы, поэтому живёт здесь, а не в диалоге
        """
        lower = [(n, n.lower()) for n in file_names]
        for name, low in lower:
            if low.endswith("_reference.smd") or ("reference" in low and low.endswith(".smd")):
                return [name]
        for name, low in lower:
            if low.endswith(".smd"):
                return [name]
        return []

    @staticmethod
    def export_selected_files(
        decompile_dir: str,
        selected_files: List[str],
        export_folder: str,
        weapon_key: str,
    ) -> str:
        export_base = ensure_directory_exists(Path(export_folder))
        src_base = Path(decompile_dir)

        selected_files = [f for f in selected_files if f]
        if not selected_files:
            raise ValueError("No files selected")

        if len(selected_files) == 1:
            rel = selected_files[0]
            src = src_base / rel
            dst = ExtractModelService._next_available_file(export_base, src.name)
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
            return str(dst)

        export_dir = ExtractModelService._next_available_dir(export_base, weapon_key)
        ensure_directory_exists(export_dir)
        for rel in selected_files:
            src = src_base / rel
            dst = export_dir / Path(rel)
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
        return str(export_dir)
