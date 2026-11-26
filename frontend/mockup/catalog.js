/*
 * Каталог: чем набивается левая панель и что происходит по выбору
 *
 * Списки, фильтры и правила видимости приходят из src/app/api.py - здесь
 * только отрисовка. Ни перечня предметов, ни условий «что показывать» в
 * представлении быть не должно, иначе они разъедутся с приложением
 *
 * Три источника, а не один: «Оружие» ходит в items() с категориями и типами,
 * «Шапки» - в hats() с поиском и классом, «Частицы» - в particle_files().
 */

import * as api from './api.js';
import { plural } from './util.js';
import { showModLibrary, bindLibraryDrop } from './catalog-library.js';
import { say } from './stage.js';
import {
  root,
  catalog,
  plist,
  pnote,
  applyRightPanel,
  closeCat,
  freshenStage,
  setStatus,
  showTf2Path,
} from './layout.js';
import {
  loadPcf,
  showEffects,
  showTree,
  currentFile,
  pickSystem,
  systemMenu,
  showParticleFrame,
  cpBox,
  setSystem,
} from './particles/index.js';
import { diagDlg, diagSay } from './diagnostics.js';
import { applyLook } from './settings.js';
import { setMode, modeControls } from './controls.js';
import { pcfNodes } from './particles/state.js';
import { startPreview, clearPreview, resetView, lastModel } from './preview.js';
import { flipList } from './motion.js';
import { clearCovers, fillCover } from './catalog-cover.js';
import { showWindowed } from './catalog-window.js';
import { addDrop, refreshDrops, closeDrops } from './catalog-fold.js';

export const els = {
  cat:   document.getElementById('cat'),
  fCat:  document.getElementById('f-cat'),
  fClass:document.getElementById('f-class'),
  fHat:  document.getElementById('f-hat'),
  fRegion: document.getElementById('f-region'),
  fCollection: document.getElementById('f-collection'),
  collection: document.getElementById('collection'),
  fSource: document.getElementById('f-source'),
  fFxCat: document.getElementById('f-fxcat'),
  fType: document.getElementById('f-type'),
  note:  document.getElementById('cat-note'),
  grid:  document.getElementById('grid'),
};

export const sel = { section: 'weapons', category: 'weapon', cls: null,
              type: null, region: null, collection: null, mode: 'normal',
              query: '' };

bindLibraryDrop();

/** Рисует ряд фильтров; null-кнопка «Все» снимает ограничение. Без all
 *  «Все» нет: категория оружия - всегда одна */
export function fillFilters(row, list, chosen, onPick, all = true) {
  row.querySelectorAll('.underlined').forEach((b) => b.remove());
  // Варианты лежат в своём контейнере (он и есть список выпадашки), а у
  // рядов без него - прямо в ряду: так строит классы окно модели для точек
  // частиц, и без запасного пути его вкладки «Шапки» и «Оружие» падали
  const into = row.querySelector('.catalog__opts') || row;
  const add = (key, name, count) => {
    const b = document.createElement('button');
    b.className = 'underlined' + (key === chosen ? ' is-active' : '');
    b.textContent = name;
    // Число рядом - сколько под этой кнопкой: без него «Лицо» может
    // оказаться пустым, и это узнают только щелчком
    if (count != null) {
      const n = document.createElement('i');
      n.className = 'underlined__n mono';
      n.textContent = count;
      b.append(n);
    }
    // Отметка сразу, не дожидаясь ответа: вкладку перерисовывает не всякий
    // выбор, а без неё щелчок выглядит пропавшим
    b.addEventListener('click', () => {
      into.querySelectorAll('.underlined').forEach((x) => x.classList.toggle('is-active', x === b));
      refreshDrops();
      onPick(key);
    });
    into.appendChild(b);
  };
  if (all) add(null, 'Все');
  list.forEach((x) => add(x.key, x.name, x.count));
  row.hidden = list.length === 0;
  refreshDrops();
}

//: Какие предметы сейчас в сетке: по нему видно, сменился ли набор
let shownKeys = '';
//: Выбранная карточка. Окно сетки пересоздаёт карточки при прокрутке, и
//: подсветка держится за ключ, а не за узел. Имя в ключе потому, что модель
//: бывает общей у нескольких предметов
let activePick = '';
const pickKey = (button, item) => `${button.dataset.flip}|${item.name}`;

export function fillGrid(list) {
  // Другой набор - с начала списка. Иначе новая категория открывалась бы с
  // середины, на рядах, иконки которых ещё ни разу не грузились. Смена
  // языка набор не меняет, и место в списке остаётся
  const keys = list.map((item) => `${item.mode}|${item.key ?? ''}`).join('\n');
  const changed = keys !== shownKeys;
  shownKeys = keys;
  // Фильтр и поиск: оставшиеся карточки доезжают на новые места (motion.js)
  const at = changed ? 0 : els.grid.scrollTop;
  flipList(els.grid, () => {
    clearCovers(els.grid);
    els.grid.hidden = list.length === 0;
    showWindowed(els.grid, list, gridCard, at);
  });
  showCount(list.length);
}

/** Карточка сетки каталога: выбор, меню системы, подсветка выбранного */
function gridCard(item) {
  const b = makePick(item, () => (item.type === 'particle'
    ? pickSystem(b, item) : choose(b, item)));
  // Правая кнопка на системе - её меню, как в дереве систем приложения
  if (item.type === 'particle') {
    b.addEventListener('contextmenu', (e) => systemMenu(e, item.key));
  }
  if (pickKey(b, item) === activePick) b.classList.add('is-active');
  return b;
}

/** Карточка предмета: обложка, имя, подпись. Одна на каталог и на выбор
 *  модели для точек частиц - второй копии обложек быть не должно */
export function makePick(item, onPick) {
  {
    const b = document.createElement('button');
    // Внутри <form method="dialog"> кнопка по умолчанию закрыла бы окно
    // раньше, чем мультиклассовая шапка дождётся выбора класса
    b.type = 'button';
    b.className = 'pick';
    b.dataset.mode = item.mode;
    b.dataset.flip = `${item.mode}|${item.key ?? ''}`;
    b.innerHTML = `<span class="pick__box"></span>
      <span class="pick__name"></span><span class="mono"></span>`;
    // Вложенность системы в PCF: ребёнок принадлежит родителю, и без
    // отступа список из 114 имён читается как каша
    if (item.depth) b.style.setProperty('--depth', item.depth);
    fillCover(b.querySelector('.pick__box'), item);
    b.querySelector('.pick__name').textContent = item.name;
    // У косметики подпись - КЛАСС, а не имя файла: у мультиклассовой шапки в
    // пути стоит подстановка (`bak_teufort_knight_%s`), и показывать её
    // человеку незачем. Длинный список сворачивается в «N классов», иначе он
    // отъедает место у названия - как в панели приложения
    // У частей персонажа класс рядом с ключом: в общем списке «Руки» у всех
    // девяти одинаковые
    b.querySelector('.mono').textContent = item.type === 'hat' ? classTag(item)
      : item.type === 'character' ? [item.label ?? item.key, item.cls].filter(Boolean).join(' · ')
      : (item.label ?? item.key);
    // Пометка у шапки с модельными стилями: у каждого стиля СВОЯ геометрия, и
    // до выбора об этом узнать было неоткуда - а стилей больше одного у 224
    // предметов из 1822. Пометка на обложке, а не в подписи: подпись занята
    // классом, и число стилей спорило бы с ним за место
    const styles = (item.styles || []).length;
    if (styles > 1) {
      const mark = document.createElement('i');
      mark.className = 'pick__styles';
      mark.textContent = styles + ' ' + plural(styles, 'стиль', 'стиля', 'стилей');
      // На самой карточке, а не в обложке: в прибитой панели обложка - метка
      // в 26 px, и пометка ложилась поверх картинки и имени. Где ей стоять в
      // каждом режиме, решает CSS
      b.appendChild(mark);
    }
    b.addEventListener('click', onPick);
    return b;
  }
}

/** Класс предмета короткой подписью: длинный список - числом */
function classTag(item) {
  const list = String(item.cls || '').split(',').map((c) => c.trim()).filter(Boolean);
  if (list.length === 0) return item.label ?? item.key;
  if (list.length === 1) return list[0];
  // Девять классов = «все»: перечислять их незачем, это половина косметики
  return list.length >= 9 ? 'все классы' : list.length + ' ' + plural(
    list.length, 'класс', 'класса', 'классов');
}

/** Сколько предметов показано. Пусто - счётчик прячется, о нуле скажет note */
export function showCount(n) {
  const el = document.getElementById('cat-count');
  el.hidden = n === 0;
  el.textContent = n + ' ' + plural(n, 'предмет', 'предмета', 'предметов');
}


async function choose(button, item) {
  els.grid.querySelectorAll('.pick').forEach((p) => p.classList.remove('is-active'));
  button.classList.add('is-active');
  activePick = pickKey(button, item);
  await openItem(item);
}

/** Открывает предмет каталога. Без карточки - так его открывает и обучение
 *  («Показать снова» ведёт на случайное оружие), путь тот же, что по щелчку */
export async function openItem(item) {
  document.querySelector('.title__name').textContent = item.name;
  document.querySelector('.title__meta').textContent =
    [item.label ?? item.key, item.cls].filter(Boolean).join(' · ');
  closeCat();
  // Ключ предмета нужен имени VPK: у косметики режим «hat» на всём разделе,
  // а модель у каждой шапки своя (см. suggest_vpk_name)
  await setMode(item.mode, item.sky || item.key || '');
  await startPreview(item);
}

//: Номер последнего запроса списка. Ответы приходят по сети и могут обогнать
//: друг друга: быстро щёлкнув по фильтрам, легко получить список от прошлого
//: выбора. Рисуем только тот ответ, который всё ещё актуален
let reloadSeq = 0;

export async function reload() {
  const seq = ++reloadSeq;
  // Косметика при первом открытии разбирает items_game целиком - это пара
  // секунд с пустым списком на экране. Ждём четверть секунды, прежде чем
  // сказать: обычный отбор укладывается в миллисекунды, и мигать словом на
  // каждую букву поиска незачем
  const wait = setTimeout(() => {
    const el = document.getElementById('cat-count');
    el.textContent = 'Читаю список…';
    el.hidden = false;
  }, 250);
  const hats = sel.section === 'hats'
    ? await api.hats({ query: sel.query || '', tf2_class: sel.cls,
                       region: sel.region, collection: sel.collection })
    : null;
  const list = hats ? hats.items
    // Поиск работает во всех разделах, а не только у косметики: поле над
    // списком одно, и «не ищет» у оружия читалось как поломка
    : await api.items({ category: sel.category, tf2_class: sel.cls,
                        weapon_type: sel.type, query: sel.query || '' });
  clearTimeout(wait);
  if (seq !== reloadSeq) return;               // выбор успел смениться
  if (hats) {
    // Группы под текущим запросом и классом, выбранная остаётся, даже если
    // под ней пусто - иначе её не снять
    const regions = hats.regions.slice();
    if (sel.region && !regions.some((r) => r.key === sel.region)) {
      regions.push({ key: sel.region, name: sel.region, count: 0 });
    }
    fillFilters(els.fRegion, regions, sel.region, pickRegion);
    fillCollections(hats.collections);
  }

  // Кастомный мод: предмет здесь - файл на диске. Список берётся не из
  // данных игры, а из библиотеки уже открытых модов
  if (sel.category === 'custom' && sel.section !== 'hats') {
    await showModLibrary();
    return;
  }

  fillGrid(list);
  els.note.hidden = list.length > 0;
  // Пусто по разной причине: фильтры или запрос ничего не нашли, или у
  // категории списка ещё нет. Опечатки поиск прощает сам (text_search.py)
  if (!list.length) {
    els.note.textContent = sel.section === 'hats' || sel.query
      ? 'Ничего не найдено - попробуйте изменить фильтр или запрос.'
      : 'Для этой категории список ещё не подключён.';
  }
}

/** Выпадающий список коллекций. Выбранная остаётся, даже если под текущим
 *  запросом в ней пусто, - как и у «Куда»: иначе её не снять */
function fillCollections(list) {
  const items = list.slice();
  if (sel.collection && !items.some((c) => c.key === sel.collection)) {
    items.push({ key: sel.collection, name: sel.collection, count: 0 });
  }
  els.collection.innerHTML = '';
  els.collection.append(new Option('Все коллекции', ''));
  for (const c of items) {
    const o = new Option(`${c.name} (${c.count})`, c.key);
    o.dataset.name = c.name;
    o.dataset.count = c.count;
    els.collection.append(o);
  }
  els.collection.value = sel.collection || '';
  refreshDrops();
  els.fCollection.hidden = items.length === 0;
}

els.collection.addEventListener('change', async () => {
  sel.collection = els.collection.value || null;
  await reload();
});

addDrop(els.fClass, { label: 'Класс' });
addDrop(els.fType, { label: 'Тип' });
addDrop(els.fFxCat, { label: 'Раздел' });
addDrop(els.fCollection, { label: 'Коллекция', select: els.collection });
addDrop(els.cat.closest('.catalog__cat'), { label: 'Файл', select: els.cat });
addDrop(els.fHat, { label: 'Скрыть', multi: true });

export async function pickRegion(key) {
  sel.region = key;
  await reload();
}

/**
 * Перерисовывает списки на другом языке, сохраняя выбор
 *
 * Имена предметов приходят из игры вместе с языком: сменив его в настройках,
 * человек ждёт список на новом языке, а не после перезапуска. Раздел, класс и
 * тип при этом остаются - перебрасывать его в «Оружие» было бы наказанием за
 * настройку.
 */
export async function relabel() {
  if (sel.section === 'particles') return;   // имена систем приходят из PCF
  await fillCategories();
  if (sel.section === 'hats') {
    await fillHatFilters();
  } else {
    if (!els.fClass.hidden) {
      fillFilters(els.fClass, await api.classes(), sel.cls, pickClass);
    }
    if (!els.fType.hidden) {
      fillFilters(els.fType, await api.weaponTypes(sel.cls), sel.type, pickType);
    }
  }
  await reload();
}

/**
 * Переключение раздела
 *
 * «Оружие» ходит в items() с категориями и типами, «Шапки» - в hats() с
 * поиском и классом: у косметики нет ни слотов оружия, ни подтипов, и
 * притворяться, что есть, значило бы показывать пустые фильтры.
 */
/**
 * Выход из сцены (от первого лица, насмешка) до остановки превью
 *
 * Остановка снимает гирлянду событием, а страница на снятую гирлянду
 * пересобирает сцену в руках. Пока сцена числилась открытой, оружие
 * возвращалось в кадр уже в чужом разделе.
 */
function leaveScene() { resetView(); }

export async function pickSection(name) {
  // Диагностика - отчёт, а не рабочее место: открываем окно и оставляем
  // текущий раздел на месте
  if (name === 'diagnostics') {
    diagDlg.showModal();
    if (!document.getElementById('diag-status').textContent) {
      diagSay('Выберите собранный VPK-мод');
    }
    return false;
  }

  const было = sel.section;
  sel.section = ['hats', 'particles', 'sounds'].includes(name)
    ? name : 'weapons';
  root.dataset.section = sel.section;
  if (было !== sel.section) {
    freshenStage();
    // Подпись прошлого предмета - сразу, до ожиданий ниже: по ней тур
    // раздела решает «предмет уже выбран» и не ждал бы выбора
    document.querySelector('.title__meta').textContent = '';
  }

  // Звуки - раздел без предмета: ни модели, ни текстур, ни каталога. Стол он
  // занимает целиком, поэтому остальную настройку разделов не проходит
  const { openSounds, closeSounds } = await import('./sounds.js');
  if (sel.section === 'sounds') {
    if (было !== 'sounds') {
      leaveScene();
      await api.stopPreview();
      clearPreview();
      say('');
    }
    await openSounds();
    return;
  }
  closeSounds();

  // Смена раздела - это уход от предмета. Воркер останавливаем ПЕРВЫМ: иначе
  // он ещё пришлёт model_ready, и текстура оружия вернётся в альбом уже поверх
  // чужого каталога
  if (было !== sel.section) {
    leaveScene();
    await api.stopPreview();
    clearPreview();
    say('');
  }

  const это_шапки = sel.section === 'hats';
  const это_частицы = sel.section === 'particles';
  showParticleFrame(это_частицы);
  cpBox.hidden = true;                 // точки живут только у эффекта
  document.getElementById('pcpbtn').classList.remove('is-active');
  document.getElementById('model-acts').hidden = это_частицы;
  applyRightPanel();      // правая панель зависит от раздела
  // Переключатель показа общий с оружием, но у эффекта правая половина -
  // не модель: там сцена с частицами. Меняем подпись, а не поведение
  const modeModel = document.querySelector('.modes [data-view="model"]');
  modeModel.textContent = это_частицы ? 'Эффект' : 'Модель';
  // У эффекта правая половина - не модель, а сцена с частицами: сцен предмета
  // (руки, насмешка) там нет вовсе
  document.querySelector('.half__bar--scenes').hidden = это_частицы;
  // Раздел открывается на «Вместе»: слева текстуры, справа эффект
  resetView();

  // Список файлов PCF - только у частиц, категории оружия - вкладками
  els.cat.parentElement.parentElement.hidden = !это_частицы;
  if (это_шапки || это_частицы) els.fCat.hidden = true;
  els.fType.hidden = true;
  els.fRegion.hidden = !это_шапки;
  els.fCollection.hidden = !это_шапки;
  els.fSource.hidden = !это_частицы;
  if (!это_частицы) els.fFxCat.hidden = true;
  els.fClass.hidden = это_частицы;
  els.fHat.hidden = !это_шапки;
  closeDrops();
  catalog.classList.toggle('no-icons', это_частицы);
  catalog.classList.toggle('catalog--tree', это_частицы);

  // Сборка VPK у частиц своя (ParticleEditorService.export_vpk) и ещё не
  // подключена. Кнопка собрала бы текстуру ОРУЖИЯ - лучше честно погасить
  setStatus('Готово', false);
  applyToolsMenu(это_частицы);

  // Заголовок называет ВЫБРАННОЕ. Уходя из раздела, чужое имя надо убрать -
  // иначе над каталогом оружия висит название эффекта
  document.querySelector('.title__name').textContent = это_частицы
    ? 'Выберите эффект' : 'Выберите предмет';
  document.querySelector('.title__meta').textContent = '';
  // Подсказка у заголовка - что именно сменит каталог: у частиц это эффект
  document.querySelector('.title__hint').textContent = это_частицы
    ? 'Сменить эффект' : 'Сменить предмет';

  if (это_частицы) {
    // Два режима одним списком: вся игра (каталог по именам, источники,
    // поиск) или один файл (дерево систем). Смешивать их на экране нельзя:
    // выпадашка файла над фильтром источников читалась как две навигации
    els.cat.innerHTML = '';
    els.cat.append(new Option('Все эффекты игры', ''));
    for (const f of await api.particleFiles()) {
      els.cat.append(new Option(f.name, f.key));
    }
    refreshDrops();
    clearCovers(els.grid);
    plist.innerHTML = '';
    pnote.hidden = false;
    setSystem('');
    // Вход в раздел - каталог эффектов по именам из игры, а не пустой
    // список с просьбой выбрать файл
    await showParticleHome();
    return;
  }


  if (это_шапки) {
    sel.category = 'hat';
    sel.cls = null;
    sel.region = null;
    sel.collection = null;
    fillFilters(els.fClass, await api.classes(), null, pickClass);
    els.fClass.hidden = false;
    await fillHatFilters();
    // Категория, а не предмет: подменять и извлекать есть что, только если
    // модель уже в кадре (каталог можно листать поверх показанного предмета)
    await setMode('hat', '', Boolean(lastModel));
    await reload();
    return;
  }

  if (name !== 'weapons') {
    clearCovers(els.grid);
    els.note.hidden = false;
    els.note.textContent = `Раздел «${name}» ещё не подключён.`;
    return;
  }
  sel.category = 'weapon';
  await fillCategories();
  await pickCategory('weapon');
}

/** Каталог частиц без запроса: дерево выбранного файла или эффекты игры */
async function showParticleHome() {
  if (els.cat.value && pcfNodes.length) showTree();
  else await showEffects('');
}

export async function pickCategory(key) {
  sel.category = key;
  sel.cls = null;
  sel.type = null;

  // Класс имеет смысл только у оружия и персонажа, тип - только у оружия
  const wantClass = key === 'weapon' || key === 'character';
  const wantType = key === 'weapon';
  els.fClass.hidden = !wantClass;
  els.fType.hidden = !wantType;

  if (wantClass) fillFilters(els.fClass, await api.classes(), null, pickClass);
  else els.fClass.querySelectorAll('.underlined').forEach((b) => b.remove());

  // Тип работает и без класса: «Ближний бой» по всем классам - нормальный
  // запрос, требовать сперва выбрать класс незачем
  if (wantType) fillFilters(els.fType, await api.weaponTypes(null), null, pickType);
  else els.fType.querySelectorAll('.underlined').forEach((b) => b.remove());

  await setMode(await api.modeFor(key), '', Boolean(lastModel));   // см. выше
  await reload();
}

/**
 * Фильтр категорий косметики: медали, Halloween, сезонные
 *
 * Это переключатели «скрыть», а не «показать»: медалей 7628 из 9504, и
 * держать их в списке по умолчанию бессмысленно. Состояние живёт в конфиге
 * приложения - то же, что видит панель шапок в окне.
 */
export async function fillHatFilters() {
  els.fHat.querySelectorAll('.underlined').forEach((b) => b.remove());
  for (const f of await api.hatFilters()) {
    const b = document.createElement('button');
    // Тот же вид, что у «Класс» и «Куда»: залитые плашки в прибитой узкой
    // колонке не помещались в строку и рвались столбиком
    b.className = 'underlined' + (f.hidden ? ' is-active' : '');
    // Имя короткое, подсказка полная: обрезать здесь по «Скрыть » значило бы
    // держать в разметке правило одного языка
    b.textContent = f.name;
    // Сколько кнопка прячет - так же, как число у фасета «Куда»
    if (f.count) {
      const n = document.createElement('i');
      n.className = 'underlined__n mono';
      n.textContent = f.count;
      b.append(n);
    }
    b.title = f.tip || f.name;
    b.addEventListener('click', async () => {
      const state = await api.setHatFilter(f.key, !b.classList.contains('is-active'));
      const now = state.find((x) => x.key === f.key);
      b.classList.toggle('is-active', now.hidden);
      refreshDrops();
      await reload();
    });
    els.fHat.querySelector('.catalog__opts').appendChild(b);
  }
  refreshDrops();
}

export async function pickClass(key) {
  sel.cls = key;
  fillFilters(els.fClass, await api.classes(), key, pickClass);

  if (sel.category === 'weapon') {
    // Набор типов сужается классом: у скаута нет часов. Выбранный тип
    // сохраняем, если он у нового класса есть, иначе снимаем - иначе список
    // молча оказался бы пустым
    const types = await api.weaponTypes(key);
    if (sel.type && !types.some((t) => t.key === sel.type)) sel.type = null;
    fillFilters(els.fType, types, sel.type, pickType);
  }
  await reload();
}

export async function pickType(key) {
  sel.type = key;
  fillFilters(els.fType, await api.weaponTypes(sel.cls), key, pickType);
  await reload();
}

// Поиск: у шапок это единственный способ найти нужное среди тысяч, поэтому
// он ищет на стороне Python, а не фильтрует показанное
let searchTimer = null;
document.querySelector('.catalog__search').addEventListener('input', (e) => {
  sel.query = e.target.value.trim();
  clearTimeout(searchTimer);
  // У частиц поиск идёт по всей игре, а не по списку предметов: запрос
  // предметов стирал дерево и говорил «список не подключён». Пустой запрос
  // возвращает дерево открытого файла или каталог эффектов
  if (sel.section === 'particles') {
    searchTimer = setTimeout(() => (sel.query ? showEffects(sel.query)
                                              : showParticleHome()), 150);
    return;
  }
  searchTimer = setTimeout(reload, 250);
});

/** Заполняет селектор категориями предметов (раздел частиц ставит туда PCF) */
export async function fillCategories() {
  fillFilters(els.fCat, await api.categories(), sel.category, pickCategory, false);
}

//: Пункт меню -> ключ в ответе controls_for. Извлечение и UV-шаблон есть
//: только у модели, сборка нескольких VPK от предмета не зависит
const TOOL_KEY = { model: 'extract_model', uv: 'extract_model',
                   texture: 'extract_texture' };

/** Меню инструментов: у эффекта свои пункты, у предмета - свои, и только
 *  те, что режим разрешает (controls_for - то же правило, что у панели).
 *  Зовётся и на старте: раздел «Оружие» открывается без pickSection, и без
 *  этого в меню висели пункты PCF при выбранном оружии */
export function applyToolsMenu(particlesSection = sel.section === 'particles') {
  document.querySelectorAll('#tools .menu__item').forEach((i) => {
    const key = TOOL_KEY[i.dataset.tool];
    i.hidden = (i.dataset.for !== 'any'
                && (i.dataset.for === 'particles') !== particlesSection)
      || (Boolean(key) && !(modeControls[key] && modeControls.has_item))
      // Сохранять можно только открытый файл: до него пункт вёл в ошибку
      || (i.dataset.need === 'pcf' && !pcfNodes.length);
  });
}

export async function boot() {
  // Внешний вид - до всего остального: иначе первые кадры страница показывает
  // светлой и перекрашивается на глазах
  applyLook((await api.settings()).values || {});
  // Правила показа - с пустым режимом: предмет ещё не выбран, и контролы
  // из разметки («Заменить модель», извлечение) не должны обещать действий
  // над ним. Меню инструментов применяется там же
  await setMode('', '', false);
  showTf2Path();
  await fillCategories();
  els.cat.addEventListener('change', () => {
    if (!els.cat.value) return showEffects(sel.query);
    // Уже открытый файл (его открыли из списка эффектов) - только дерево:
    // разбор заново выбросил бы несохранённые правки без вопроса
    if (els.cat.value === currentFile()) return showTree();
    return loadPcf(els.cat.value);
  });
  await pickCategory('weapon');
  // Страницу подняли заново после смены языка - возвращаемся в тот же раздел
  let back = '';
  try { back = sessionStorage.getItem('section') || ''; sessionStorage.removeItem('section'); } catch {}
  if (back) document.querySelector(`.chrome__nav [data-section="${back}"]`)?.click();
}

/** Переход в раздел не щелчком: мод открывается там, где живёт то, что он
 *  заменяет. Уже там - ничего не трогаем: смена раздела гасит превью */
export async function goSection(name) {
  if (sel.section === name) return;
  await pickSection(name);
  document.querySelectorAll('.chrome__nav .underlined')
          .forEach((b) => b.classList.toggle('is-active', b.dataset.section === name));
}

// Разделы в шапке: «Оружие», «Шапки» и «Частицы» - разные источники каталога.
// «Диагностика» раздела не занимает (открывает отчёт), поэтому подсветку
// двигаем только если раздел действительно сменился
document.querySelector('.chrome__nav').addEventListener('click', async (e) => {
  const btn = e.target.closest('.underlined');
  if (!btn) return;
  // Щелчок по разделу, где уже стоишь, - не уход из него: настройка раздела
  // прошла бы заново и стёрла заголовок открытого предмета, а сам предмет
  // остался бы в кадре
  if (btn.dataset.section === sel.section) return;
  // Ключ из data-section, а не подпись: подпись переводится
  if (await pickSection(btn.dataset.section) === false) return;
  document.querySelectorAll('.chrome__nav .underlined')
          .forEach((b) => b.classList.remove('is-active'));
  btn.classList.add('is-active');
});
