/*
 * Открытие чужого мода: VPK, ZIP или папка, и какие его модели показать
 *
 * Карточки библиотеки рисует каталог (showModLibrary), здесь - путь от файла
 * до мода в кадре. Пополнив библиотеку, модуль говорит об этом событием
 * `mods:changed`: каталог перерисует её сам, а этот модуль о нём не знает.
 */

import * as api from './api.js';
import { ask } from './ask.js';
import { say, sayError, withViewer } from './stage.js';
import { chooseFile } from './util.js';
import { closeCat } from './layout.js';
import { setMode } from './controls.js';
import { goSection } from './catalog.js';
import { clearPreview } from './preview.js';

/**
 * Показ чужого мода из VPK
 *
 * Предмет не меняется: мод накладывается поверх текущего выбора, его модель и
 * текстуры становятся тем, что на экране, а сам файл уходит в сборку
 * источником.
 *
 * Возвращает, открылся ли мод: работу по моду восстанавливают только поверх него
 */
export async function openMod(mod) {
  const model = await pickModModel(mod);
  if (model === null) return false;
  // Мод-шапка живёт на странице шапок: там она на голове, на персонаже и с
  // краской. Раздел меняется ДО загрузки - смена раздела гасит превью. Отказ
  // приходит раньше: экран остаётся нетронутым
  const target = await api.modTarget(mod.path, model);
  if (target.error) { sayError(target.error); return false; }
  const hat = target.kind === 'cosmetic' ? target.hat : null;
  await goSection(target.kind === 'cosmetic' ? 'hats' : 'weapons');
  // Сцена «На персонаже» и всё прочее - про прошлый предмет
  clearPreview();
  say(`Разбор ${mod.name}…`);
  // Как у предмета каталога: вьювер прячет своё «Выберите предмет» и
  // крутит кубик, а ход работы пишет подпись страницы. Без этого две надписи
  // ложились одна на другую
  withViewer((w) => w.showLoading());
  const res = await api.loadVpkMod(mod.path, model);
  if (res.error) {
    sayError(res.error);
    withViewer((w) => w.stopLoading());
    return false;
  }
  showModAsItem(mod.name, hat);
  return true;
}

//: Подписи групп моделей мода. Ключи задаёт Python (vpk_mod_models.KINDS)
const MODEL_KINDS = {
  weapon: 'Оружие', garland: 'Гирлянды', arms: 'Руки', player: 'Персонажи',
  cosmetic: 'Косметика', projectile: 'Снаряды', pickup: 'Подбираемое', other: 'Прочее',
};

/**
 * Какую модель мода показать: путь MDL, '' - на выбор приложения (само
 * оружие или первая), null - отказались
 *
 * Спрашиваем, только когда моделей больше одной. В сборку мод уходит целиком
 * при любом выборе - это только то, что видно в кадре
 */
async function pickModModel(mod) {
  let list = [];
  try {
    list = (await api.vpkModModels(mod.path)).models || [];
  } catch {
    list = [];
  }
  if (list.length < 2) return '';
  const last = lastChoice(mod.name);
  const before = list.some((m) => m.path === last) ? last : list[0].path;
  const picked = await ask({
    title: 'Какую модель показать?',
    text: 'В моде несколько моделей. В сборку он уйдёт целиком - это только то, что будет в кадре',
    ok: 'Показать',
    list: list.map((m) => ({ label: m.name, value: m.path, hint: m.path,
                             group: MODEL_KINDS[m.kind] || m.kind,
                             selected: m.path === before })),
  });
  if (picked === null) return null;
  rememberChoice(mod.name, picked);
  return picked;
}

// Прошлый выбор модели - отмеченным по умолчанию: открывая тот же мод,
// искать её заново незачем. Только удобство: хранилища может не быть
// (закрытый профиль), тогда окно отметит первую модель
const CHOICE_KEY = 'modModel';

function lastChoice(name) {
  try {
    return JSON.parse(localStorage.getItem(CHOICE_KEY) || '{}')[name] || '';
  } catch {
    return '';
  }
}

function rememberChoice(name, picked) {
  try {
    const all = JSON.parse(localStorage.getItem(CHOICE_KEY) || '{}');
    all[name] = picked;
    localStorage.setItem(CHOICE_KEY, JSON.stringify(all));
  } catch {
    // нет хранилища - в следующий раз спросим с первой моделью
  }
}

/** Выбирает файл с диска: он попадает в библиотеку и сразу открывается */
export async function pickVpkMod() {
  const file = await chooseFile('.vpk,.zip');
  if (!file) return;

  say(`Разбор ${file.name}…`);
  // Сохраняем ДО открытия: временную копию, в которую браузер положил файл,
  // рано или поздно чистят, и вернуться к моду было бы не по чему
  const path = await api.upload(file);
  if (/\.zip$/i.test(file.name)) { await importAndOpen(path); return; }
  const saved = await api.addMod(path);
  if (saved.error) { sayError(saved.error); return; }
  await openMod({ name: saved.name, path: saved.path });
}

/** Папка мода, как её кладут в tf/custom: пакуется в VPK библиотеки */
export async function pickModFolder() {
  const res = await api.pickFolder('');
  if (res.error) { sayError(res.error); return; }
  if (!res.path) return;
  say('Упаковка мода…');
  await importAndOpen(res.path);
}

/**
 * ZIP или папка - в библиотеку, и открыть. Модов внутри бывает несколько
 * (архив со сборником): в библиотеку ложатся все, открыть - какой выбрать
 */
async function importAndOpen(path) {
  const res = await api.importMod(path);
  if (res.error) { sayError(res.error); return; }
  const mods = res.mods || [];
  let mod = mods[0];
  if (mods.length > 1) {
    const name = await ask({
      title: 'Какой мод открыть?',
      text: 'Внутри несколько модов - все они уже в библиотеке',
      ok: 'Открыть',
      list: mods.map((m) => ({ label: m.name, value: m.name })),
    });
    document.dispatchEvent(new Event('mods:changed'));
    mod = mods.find((m) => m.name === name);
    if (!mod) return;
  }
  await openMod(mod);
}

/**
 * Показанный мод становится выбранным предметом: заголовок называет его
 *
 * Мод-шапка называется шапкой, которую заменяет, и получает её контролы
 * («На персонаже», краска). Собирается он всё равно как мод: сборку решает
 * сеанс, а не режим страницы
 */
function showModAsItem(name, hat) {
  document.querySelector('.title__name').textContent = hat ? hat.name : name;
  document.querySelector('.title__meta').textContent =
    hat ? `мод из VPK: ${name}` : 'мод из VPK';
  closeCat();
  setMode(hat ? 'hat' : 'custom', hat ? hat.key : '');
}
