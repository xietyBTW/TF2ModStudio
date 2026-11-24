/*
 * Обложка карточки - снимок модели из вьювера (моды библиотеки, свои работы)
 *
 * Когда снимать, решает вызывающий: options уходят во вьювер как есть (см.
 * snapshotWaiter в src/static/js/viewer_snapshot.js). Здесь только дорога
 * от кадра до карточки: снимок, запись, перерисовка раздела
 */

import { viewer } from './stage.js';
import { root } from './layout.js';

/** Класть ли модель набок: оружие - да, шапка стоит. Решается в момент
 *  снимка - мод-шапка уезжает на страницу шапок уже после начала ожидания */
export const layFlat = () => root.dataset.section !== 'hats';

/**
 * Ждёт успокоения сцены, снимает и отдаёт PNG в save(png)
 *
 * Не вышло - обложкой остаётся прежняя, снимем в следующий раз, поэтому
 * молча: карточка не стоит того, чтобы мешать работе
 */
export async function shootCover(options, save) {
  const shot = viewer()?.snapshotWhenSettled?.(options);
  const png = shot ? await shot : null;
  if (!png) return;
  try {
    const res = await save(png);
    if (res?.error) return;
  } catch {
    return;
  }
  // Каталог подписан и перерисует раздел, если он открыт
  document.dispatchEvent(new Event('mods:changed'));
}
