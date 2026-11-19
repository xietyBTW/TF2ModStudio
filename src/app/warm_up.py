"""
Прогрев индексов игры в фоне, пока страница рисуется

Каталог VPK (131 тысяча записей у tf2_textures + tf2_misc) разбирается
полсекунды на архив, а нужен всем разделам разом: первый вход в звуки стоил
1,3 с, в частицы - 1,6 с, и три четверти этого - архивы. Кэши общие на потоки
(см. vpk_cache), так что грев из фонового потока достаётся всем. Игры может
не быть на месте - тогда тихо
"""

from __future__ import annotations

import threading
from typing import TYPE_CHECKING

from src.shared.logging_config import get_logger

if TYPE_CHECKING:
    from src.app.session import AppSession

logger = get_logger(__name__)


def start(host: "AppSession") -> None:
    """Запускает прогрев своим потоком и сразу возвращается"""
    threading.Thread(target=_warm, args=(host,), name='vpk-warm', daemon=True).start()


def _warm(host: "AppSession") -> None:
    try:
        from src.config.app_config import AppConfig
        from src.data import stock_loadout, viewmodel_anims
        from src.data.hats_parser import parse_hats
        from src.data.item_skin_styles import item_skin_styles
        from src.services import decompile_cache, game_texture_index
        from src.services.particle_editor_service import ParticleEditorService
        from src.services.tf2_paths import TF2Paths
        from src.services.vtf_preview_service import open_vpks

        paths = host.tf2_paths()
        lang = AppConfig.load_config().get('language') or 'ru'
    except Exception as exc:                      # noqa: BLE001
        logger.debug(f"прогрев не начался: {exc}")
        return
    if 'error' in paths:
        return
    root = paths['root']
    steps = [
        lambda: open_vpks([paths['misc_vpk'], paths['textures_vpk'],
                           *TF2Paths.resolve_hl2_vpks(root),
                           *host.sounds.sound_vpks(paths['tf_dir'])]),
        # Банки краски - разбор items_game на секунду, первому щелчку по
        # «Краске» ждать его незачем
        lambda: host.paints(lang),
        # Индекс моделей из items_game: по нему у каждого оружия спрашивают
        # гирлянды, и первый выбор предмета не должен ждать разбора восьми
        # мегабайт
        lambda: viewmodel_anims.anim_index(root),
        # Каталоги разделов: без них первый вход в звуки ждал 0,7 с, в шапки
        # и частицы - по 0,15
        lambda: host.sounds.sounds(lang=lang),
        lambda: parse_hats(root, lang),
        lambda: ParticleEditorService.list_game_pcfs(root),
        # Первый выбранный предмет иначе ждал их сам: стили скинов 0,25 с,
        # список кэша моделей до 1,6 с с холодного диска, стоковое снаряжение
        # сцены «На персонаже» 0,5 с
        lambda: item_skin_styles(root),
        decompile_cache.warm_index,
        lambda: stock_loadout.loadout('scout', root),
        # Таблица «текстура -> модели» для модов без модели. Из кэша
        # мгновенно, после обновления игры - пара секунд
        lambda: game_texture_index.load(paths['misc_vpk']),
        # Индекс эффектов частиц: с нуля (новый ПК, обновление игры) это
        # 13 с, и при первом входе в частицы список стоял без файлов. Здесь
        # только запуск своего потока, ждать его нечего
        lambda: ParticleEditorService.system_index(root),
    ]
    # Шаги не зависят друг от друга: упавший не отменяет остальные
    for step in steps:
        try:
            step()
        except Exception as exc:                  # noqa: BLE001
            logger.debug(f"прогрев: шаг не удался: {exc}")
