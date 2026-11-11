"""
Сервис для объединения нескольких VPK файлов в один
"""

import os
import shutil
from pathlib import Path
from typing import List, Tuple, Dict, Optional, Callable
from src.shared.logging_config import get_logger
from src.shared.file_utils import ensure_directory_exists, copy_file_safe
from src.shared.validators import sanitize_path

logger = get_logger(__name__)

try:
    import vpk
    VPK_AVAILABLE = True
except ImportError:
    VPK_AVAILABLE = False
    vpk = None


class MergeVPKService:
    """Сервис для объединения VPK файлов"""
    
    @staticmethod
    def merge_vpk_files(
        vpk_files: List[Path],
        output_filename: str,
        export_folder: str = "export",
        language: str = "en",
        should_cancel: Optional[Callable[[], bool]] = None
    ) -> Tuple[bool, str]:
        """
        Объединяет несколько VPK файлов в один
        
        Args:
            vpk_files: Список путей к VPK файлам для объединения
            output_filename: Имя выходного VPK файла
            export_folder: Папка для экспорта
            language: Язык для сообщений об ошибках
            
        Returns:
            Tuple[success, message]
        """
        from src.data.translations import TRANSLATIONS
        t = TRANSLATIONS.get(language, TRANSLATIONS['en'])
        
        if not VPK_AVAILABLE:
            return False, t.get('vpk_library_not_available', 'VPK library not available')
        
        if not vpk_files:
            return False, t.get('no_vpk_files_selected', 'No VPK files selected')
        
        # Проверяем существование всех файлов
        for vpk_file in vpk_files:
            if not vpk_file.exists():
                return False, t.get('vpk_file_not_found', 'VPK file not found: {path}').format(path=vpk_file)
        
        # Временная папка - в системном %TEMP%, как у сборки (BuildContext):
        # пути внутри модов длинные, а vpk.exe не открывает длиннее 260 символов
        import tempfile
        temp_dir = Path(tempfile.mkdtemp(prefix="tf2sg_merge_"))
        merged_root = temp_dir / "vpkroot"
        
        try:
            if should_cancel and should_cancel():
                return False, t.get('merge_cancelled', 'Объединение отменено пользователем')

            ensure_directory_exists(merged_root)
            
            # Извлекаем и объединяем каждый VPK
            logger.info(f"Начинаем объединение {len(vpk_files)} VPK файлов")
            
            for i, vpk_file in enumerate(vpk_files, 1):
                if should_cancel and should_cancel():
                    return False, t.get('merge_cancelled', 'Объединение отменено пользователем')

                logger.info(f"[{i}/{len(vpk_files)}] Обрабатываем: {vpk_file.name}")
                
                # Извлекаем содержимое VPK во временную папку
                extract_dir = temp_dir / f"extract_{i}"
                ensure_directory_exists(extract_dir)
                
                try:
                    # Открываем VPK файл
                    vpk_archive = vpk.open(str(vpk_file))
                    
                    # Извлекаем все файлы
                    for file_path in vpk_archive:
                        if should_cancel and should_cancel():
                            return False, t.get('merge_cancelled', 'Объединение отменено пользователем')

                        # Получаем содержимое файла
                        file_data = vpk_archive[file_path].read()
                        
                        # Создаем путь в извлеченной директории
                        try:
                            extract_file_path = Path(sanitize_path(file_path, extract_dir))
                        except ValueError as e:
                            logger.warning(f"Недопустимый путь при извлечении {file_path}: {e}")
                            continue
                        ensure_directory_exists(extract_file_path.parent)
                        
                        # Записываем файл
                        with open(extract_file_path, 'wb') as f:
                            f.write(file_data)
                    
                    # Объединяем извлеченные файлы в merged_root
                    MergeVPKService._merge_directory(extract_dir, merged_root)
                    
                    logger.info(f"Файлы из {vpk_file.name} объединены")
                    
                except Exception as e:
                    logger.error(f"Ошибка при извлечении {vpk_file.name}: {e}", exc_info=True)
                    return False, t.get('error_extracting_vpk', 'Error extracting VPK: {file}').format(file=vpk_file.name)
            
            if should_cancel and should_cancel():
                return False, t.get('merge_cancelled', 'Объединение отменено пользователем')

            # Создаем новый VPK из объединенной папки
            logger.info("Создаем объединенный VPK файл...")
            vpk_path = MergeVPKService._create_vpk_from_directory(
                merged_root,
                output_filename,
                export_folder,
                language,
                should_cancel=should_cancel
            )
            
            if not vpk_path:
                if should_cancel and should_cancel():
                    return False, t.get('merge_cancelled', 'Объединение отменено пользователем')
                return False, t.get('error_creating_merged_vpk', 'Error creating merged VPK file')
            
            # Очищаем временные файлы
            try:
                shutil.rmtree(temp_dir)
            except Exception as e:
                logger.warning(f"Не удалось удалить временную директорию: {e}")
            
            success_msg = t.get('merge_vpk_success', 'VPK files successfully merged: {path}').format(path=vpk_path)
            return True, success_msg
            
        except Exception as e:
            logger.error(f"Ошибка при объединении VPK: {e}", exc_info=True)
            # Пытаемся очистить временные файлы
            try:
                if temp_dir.exists():
                    shutil.rmtree(temp_dir)
            except Exception:
                pass
            return False, t.get('error_merging_vpk', 'Error merging VPK files: {error}').format(error=str(e))
        finally:
            if should_cancel and should_cancel():
                try:
                    if temp_dir.exists():
                        shutil.rmtree(temp_dir)
                except Exception:
                    pass
    
    @staticmethod
    def _merge_directory(source_dir: Path, target_dir: Path):
        """
        Объединяет содержимое source_dir в target_dir
        
        Если папки с одинаковыми именами существуют, они объединяются рекурсивно.
        Файл, который уже положил мод выше в списке, остаётся его: игра читает
        файл только по точному пути, и копия под другим именем была бы мусором
        в VPK (см. merge_plan.conflicts - там же это видно человеку)
        
        Args:
            source_dir: Исходная директория
            target_dir: Целевая директория
        """
        if not source_dir.exists():
            return
        
        # Проходим по всем элементам в исходной директории
        for root, dirs, files in os.walk(source_dir):
            # Получаем относительный путь от source_dir
            rel_root = Path(root).relative_to(source_dir)
            target_root = target_dir / rel_root
            
            # Создаем директорию в целевой папке
            ensure_directory_exists(target_root)
            
            # Копируем файлы
            for file_name in files:
                source_file = Path(root) / file_name
                target_file = target_root / file_name
                
                if target_file.exists():
                    logger.debug(f"{rel_root / file_name}: остаётся из мода выше в списке")
                    continue
                # Копируем файл
                copy_file_safe(source_file, target_file)
    
    @staticmethod
    def _create_vpk_from_directory(
        vpkroot_dir: Path,
        filename: str,
        export_folder: str = "export",
        language: str = "en",
        should_cancel: Optional[Callable[[], bool]] = None,
    ) -> Optional[str]:
        """
        Создаёт VPK файл из директории vpkroot.
        Делегирует в PackagingService.pack_directory - единственное место вызова vpk.exe
        """
        if should_cancel and should_cancel():
            return None

        from src.services.packaging_service import PackagingService
        return PackagingService.pack_directory(
            vpkroot_dir=vpkroot_dir,
            filename=filename,
            export_folder=export_folder,
            language=language,
        )
