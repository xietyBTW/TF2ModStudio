/*
 * Категория «Кастомный мод»: библиотека модов из VPK и сохранённые работы
 *
 * Свой модуль, а не раздел catalog.js: здесь не каталог игры, а файлы
 * человека - со своими обложками-снимками, броском файлов на сетку и
 * открытием работ. Сетку и выбор раздела модуль берёт у каталога
 */

import * as api from './api.js';
import { fileSize, plural } from './util.js';
import { openMod, pickVpkMod, pickModFolder, dropModFiles } from './mod-library.js';
import { shootCover, layFlat } from './cover-shot.js';
import { ask } from './ask.js';
import { say, sayError } from './stage.js';
import { closeCat } from './layout.js';
import { setMode } from './controls.js';
import { startHatWork, startPreview } from './preview.js';
import { clearCovers } from './catalog-cover.js';
import { els, sel, showCount } from './catalog.js';

// Импорт ZIP или папки пополнил библиотеку - перерисовать, если она открыта
document.addEventListener('mods:changed', () => {
  if (sel.category === 'custom') showModLibrary();
});

/**
 * Файлы модов можно бросить на библиотеку. Она на экране, пока в сетке
 * стоит её дверь: отдельный флаг пришлось бы гасить при каждой смене раздела
 *
 * Зовёт каталог, когда его сетка уже есть: модули импортируют друг друга,
 * и на верхнем уровне этого модуля `els` ещё не готов
 */
export function bindLibraryDrop() {
  const grid = els.grid;
  const libraryShown = () => grid.querySelector('.pick--add') !== null;
  const carriesFiles = (e) => [...(e.dataTransfer?.types || [])].includes('Files');

  grid.addEventListener('dragover', (e) => {
    if (!libraryShown() || !carriesFiles(e)) return;
    e.preventDefault();
    grid.classList.add('is-drop');
  });
  grid.addEventListener('dragleave', (e) => {
    if (!grid.contains(e.relatedTarget)) grid.classList.remove('is-drop');
  });
  grid.addEventListener('drop', (e) => {
    grid.classList.remove('is-drop');
    if (!libraryShown() || !carriesFiles(e)) return;
    e.preventDefault();
    dropModFiles(e.dataTransfer);
  });
}

/**
 * Категория «Кастомный мод»: дверь к файлу и всё, что через неё уже прошло
 *
 * Мод - это ВЫБОР предмета, а не действие над загруженным: он заменяет собой
 * и модель, и текстуры. Поэтому живёт в каталоге рядом с оружием и шапками, а
 * не в ряду кнопок под моделью.
 */
export async function showModLibrary() {
  clearCovers(els.grid);
  els.note.hidden = false;
  els.note.textContent = 'Свои работы и моды из VPK. Предмет из списка оружия '
    + 'открывается игровым - сохранённая работа открывается отсюда.';

  // Сверху моды из VPK (первой - дверь к новому файлу), под полосой - свои
  // работы: в одной сетке они путались, хвост модов уезжал в ряд к работам.
  // Дверь одна: файл - кликом по карточке или броском на сетку, папка -
  // ссылкой. Две одинаковые карточки читались как два разных действия
  const add = document.createElement('button');
  add.className = 'pick pick--open pick--add';
  add.innerHTML = `<span class="pick__box"></span>
    <span class="pick__name">Добавить мод…</span>
    <span class="mono">VPK или ZIP, можно перетащить</span>
    <span class="pick__alt">или папку как в tf/custom…</span>`;
  add.addEventListener('click', pickVpkMod);
  add.querySelector('.pick__alt').addEventListener('click', (e) => {
    e.stopPropagation();                    // не открыть заодно выбор файла
    pickModFolder();
  });
  els.grid.append(add);

  const mods = await api.modLibrary();
  for (const mod of mods) {
    const card = document.createElement('button');
    card.className = 'pick pick--mod';
    card.innerHTML = `<span class="pick__box"></span>
      <span class="pick__name"></span><span class="mono"></span>`;
    card.querySelector('.pick__name').textContent = mod.name;
    card.querySelector('.mono').textContent = fileSize(mod.size);
    card.addEventListener('click', () => openMod(mod, { shoot: !mod.shot }));

    // Удаление - на самой карточке: искать папку на диске ради этого не
    // должно быть нужно. Спрашиваем подтверждение: файл уйдёт насовсем
    const drop = document.createElement('span');
    drop.className = 'pick__drop';
    drop.title = 'Убрать из библиотеки (исходный файл останется)';
    drop.textContent = '×';
    drop.addEventListener('click', async (e) => {
      e.stopPropagation();                  // не открыть заодно
      // Про исходный файл говорим прямо: в библиотеке лежит НАША копия, и
      // «убрать» здесь не трогает то, что человек когда-то выбрал на диске
      const yes = await ask({
        title: 'Убрать мод из библиотеки',
        text: `${mod.name}\nУдалится копия в библиотеке. Исходный файл, который вы открывали, останется на месте.`,
        ok: 'Убрать',
      });
      if (!yes) return;
      const res = await api.removeMod(mod.name);
      if (res.error) { sayError(res.error); return; }
      await showModLibrary();
    });
    card.append(drop);
    els.grid.append(card);
    // После вставки: обложка проверяет, что карточка ещё в сетке
    showModCover(card, mod);
  }

  const rule = document.createElement('div');
  rule.className = 'catalog__rule';
  rule.textContent = 'Мои работы';
  els.grid.append(rule);
  const works = await showWorks();
  if (!works) rule.remove();
  // Счётчик строится мимо fillGrid, обновить его надо самим: иначе тут
  // висит число от прошлой категории
  showCount(works + mods.length);
}

/**
 * Обложка и подпись мода на карточке
 *
 * Обложка по убыванию: снимок модели (есть, если мод открывали), иконка
 * предмета, который мод заменяет, основная текстура мода. Подпись - тот же
 * предмет: по имени файла мода не понять, что он меняет. Всё, чего нет
 * готовым, просится по одной карточке и не держит список
 */
async function showModCover(card, mod) {
  const box = card.querySelector('.pick__box');
  // Карточка могла уехать, пока ждали ответ (удалили, сменили раздел)
  const put = (src, fallback) => { if (card.isConnected) box.append(coverImg(src, fallback)); };
  const texture = async () => {
    const res = await api.modIcon(mod.name);
    if (res.icon) put(api.fileUrl(res.icon));
  };
  if (mod.shot) put(api.fileUrl(mod.icon));

  let info = {};
  try {
    info = await api.modInfo(mod.name);
  } catch {
    // не узнали - карточка остаётся с размером файла
  }
  if (info.title && card.isConnected) {
    card.querySelector('.mono').textContent = info.title;
    card.title = `${mod.name} - ${fileSize(mod.size)}`;
  }
  if (mod.shot) return;
  if (info.icon) put(api.iconUrl(info.icon), texture);
  else await texture();
}

/** Обложка библиотеки. Каталог прячет картинку до is-loaded (без мигания
 *  недогруженной), и без этого класса обложка оставалась невидимой.
 *  fallback - чем заменить, если картинки нет */
function coverImg(src, fallback = null) {
  const img = document.createElement('img');
  img.className = 'pick__icon';
  img.loading = 'lazy';
  img.alt = '';
  img.addEventListener('error', () => { img.remove(); fallback?.(); });
  img.addEventListener('load', () => img.classList.add('is-loaded'), { once: true });
  img.src = src;
  return img;
}

/**
 * Сохранённые работы - карточками, как предметы
 *
 * Работа не возвращается молча при открытии предмета: список оружия
 * показывает игру, а свой обрез открывается отсюда, иначе к игровому было бы
 * не вернуться.
 */
async function showWorks() {
  const list = await api.works();
  if (!list.length) return 0;

  for (const work of list) {
    const card = document.createElement('button');
    card.className = 'pick pick--work';
    card.innerHTML = `<span class="pick__box"></span>
      <span class="pick__name"></span><span class="mono"></span>`;
    card.querySelector('.pick__name').textContent = work.name;
    card.querySelector('.mono').textContent = whenSaved(work.saved_at);
    // Снимок модели с правками, а до первого снимка - иконка предмета
    const cover = work.shot ? api.fileUrl(work.shot) + '&v=' + work.shot_at
      : work.icon ? api.iconUrl(work.icon) : '';
    if (cover) card.querySelector('.pick__box').append(coverImg(cover));
    card.addEventListener('click', () => openWork(work));

    // Удаление - как у модов, на самой карточке. Работа уходит насовсем:
    // копии, как у мода из VPK, у неё нет
    const drop = document.createElement('span');
    drop.className = 'pick__drop';
    drop.title = 'Удалить работу';
    drop.textContent = '×';
    drop.addEventListener('click', async (e) => {
      e.stopPropagation();                  // не открыть заодно
      const yes = await ask({
        title: 'Удалить работу',
        text: `${work.name}\nРабота удалится насовсем вместе с её файлами. Игровой предмет не изменится.`,
        ok: 'Удалить',
      });
      if (!yes) return;
      const res = await api.deleteWork(work.key);
      if (res.error) { sayError(res.error); return; }
      await showModLibrary();
    });
    card.append(drop);
    els.grid.append(card);
  }
  return list.length;
}

/** Когда сохранено - словами: точное время тут ничего не решает */
function whenSaved(stamp) {
  const days = Math.floor((Date.now() / 1000 - (stamp || 0)) / 86400);
  if (days <= 0) return 'сегодня';
  if (days === 1) return 'вчера';
  // Целой фразой: словарь узнаёт «{} дня назад», а слово по отдельности
  // оставляло бы «3 days назад»
  return plural(days, `${days} день назад`, `${days} дня назад`, `${days} дней назад`);
}

/**
 * Открывает работу: тот же предмет, но с восстановленными правками
 *
 * Ключ модели передаём явно. Из режима его выводит Python, но только у
 * оружия: у шапки модель задаётся выбором в каталоге, и без ключа работа по
 * шапке не открывалась вовсе. Мод из VPK - вообще не предмет каталога:
 * он грузится файлом, а правки к нему возвращаются следом.
 */
async function openWork(work) {
  document.querySelector('.title__name').textContent = work.name;
  document.querySelector('.title__meta').textContent = 'сохранённая работа';
  closeCat();
  say('Открываю работу…');
  // Обложка обновляется при каждом открытии: работа и после «Сохранить»
  // молча дописывается автосохранением. Ждём новую модель и всё, что
  // восстановление поставит следом (своя модель работы)
  shootCover({ lay: layFlat, fresh: true, follow: true },
             (png) => api.saveWorkShot(work.key, png));

  if (work.mod) {
    // Мод не открылся (отказ, отмена выбора модели) - в кадре прошлый
    // предмет, и работа легла бы на него
    if (!await openMod({ name: work.name, path: work.mod })) return;
    const back = await api.restoreWork();
    if (back.error) sayError(back.error);
    return;
  }

  await setMode(work.mode, work.item_key || '');
  if (work.mode === 'hat') { await startHatWork(work); return; }
  if (work.mode === 'skybox') {
    await startPreview({ type: 'skybox', key: work.item_key }, { restore: true });
    return;
  }
  const res = await api.loadPreview(work.mode, null, work.item_key || null,
                                    work.per_class || null, null, true);
  if (res.error) sayError(res.error);
}
