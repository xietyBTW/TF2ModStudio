/*
 * Экспорт текстуры одной карточки по правой кнопке: оружие, шапки, части и
 * частицы. Файл ложится в папку экспорта в формате из настроек
 */

import * as api from './api.js';
import { t } from './i18n.js';
import { contextMenu } from './menu.js';
import { notifyApp } from './app-note.js';

/** Пункты экспорта. Оригинала нет в меню, пока на карточке и так он */
export function exportItems(hasOwn = true) {
  const items = [{ label: 'Экспортировать текстуру', value: 'export' }];
  if (hasOwn) items.push({ label: 'Экспортировать оригинальную текстуру', value: 'export_original' });
  return items;
}

/** Выполняет пункт экспорта. false - выбран пункт не про экспорт */
export async function runExport(choice, save) {
  if (choice !== 'export' && choice !== 'export_original') return false;
  const res = await save(choice === 'export_original');
  if (res.error) notifyApp(res.error, 'error');
  else notifyApp(t('Текстура сохранена в папку экспорта: {}').replace('{}', res.name));
  return true;
}

/** Меню карточки альбома (оружие, шапки, части). `hasOwn` - на карточке не
 *  игровой оригинал (view_state.own_cards). Пустой карточке (стиль без своей
 *  текстуры) экспортировать нечего - меню нет вовсе */
export async function cardMenu(e, name, hasOwn, hasImage = true) {
  if (!hasImage) { e.preventDefault(); return; }
  const chosen = await contextMenu(e, exportItems(hasOwn));
  await runExport(chosen, (original) => api.exportCardTexture(name, original));
}
