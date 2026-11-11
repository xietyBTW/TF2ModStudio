/*
 * Панель свойств выбранной системы
 *
 * Что показать - крутилки или файл как есть - решает переключатель режима.
 * Список параметров приходит из Python готовым: схема одна на панель
 * приложения и на эту страницу. Здесь раскладка простого режима: быстрые
 * правки всего эффекта, фильтр, разделы; сами карточки - cards.js
 */

import * as api from '../api.js';
import { t } from '../i18n.js';
import { plist, pnote } from '../layout.js';
import { pSystem, pMode, setSystem, setMode } from './state.js';
import { quickEdit } from './fields.js';
import { paramCard, isChanged } from './cards.js';
import { pfind, filterExpert, showExpert } from './expert.js';
import { syncHistory } from './playback.js';

//: Фильтр карточек: все, только те, что есть в системе, только изменённые
const FILTERS = [
  { key: 'all', label: 'Все' },
  { key: 'present', label: 'В системе', tip: 'Только то, что уже есть в этой системе' },
  { key: 'changed', label: 'Изменённые', tip: 'Только то, что отличается от игры' },
];
//: Быстрые правки всего эффекта: [ключ, подпись, меньше, больше, подсказка]
const QUICK = [
  ['scale', 'Масштаб', 'Мельче', 'Крупнее',
   'Весь эффект крупнее или мельче: размер частиц, область, скорости и силы вместе'],
  ['density', 'Плотность', 'Реже', 'Гуще',
   'Больше или меньше частиц во всём эффекте: темп, залпы и потолок вместе'],
  ['tempo', 'Темп', 'Медленнее', 'Быстрее',
   'Весь эффект быстрее или медленнее: время жизни, скорости и ускорения согласованно'],
];

//: Вид панели: пояснения под крутилками, фильтр, свёрнутые разделы (битами
//: по порядку разделов). Хранится в общем конфиге (particle_simple_*)
const view = { hints: false, filter: 'all', folded: 0 };

/** Вид из конфига: зовётся из настроек вместе с остальной раскладкой */
export function setSimpleView(bits, folded) {
  const b = Number(bits) || 0;
  view.hints = Boolean(b & 1);
  view.filter = FILTERS[(b >> 1) & 3]?.key || 'all';
  view.folded = Number(folded) || 0;
}

function saveView() {
  const filter = Math.max(0, FILTERS.findIndex((f) => f.key === view.filter));
  api.setUiState('particle_simple_view', (view.hints ? 1 : 0) | (filter << 1)).catch(() => {});
  api.setUiState('particle_simple_folded', view.folded).catch(() => {});
}

/** Показывает ли фильтр карточку */
function passes(param) {
  if (view.filter === 'present') return param.value !== null;
  if (view.filter === 'changed') return isChanged(param);
  return true;
}

function button(cls, text, tip, onClick) {
  const b = document.createElement('button');
  b.type = 'button';
  b.className = cls;
  b.textContent = t(text);
  if (tip) b.title = t(tip);
  b.addEventListener('click', onClick);
  return b;
}

/** Быстрые правки, фильтр и пояснения - строкой над разделами */
function toolbar(system) {
  const bar = document.createElement('div');
  bar.className = 'spbar';
  const quick = document.createElement('div');
  quick.className = 'spbar__quick';
  const head = document.createElement('span');
  head.className = 'label';
  head.textContent = t('Весь эффект');
  quick.append(head);
  for (const [kind, name, less, more, tip] of QUICK) {
    const box = document.createElement('span');
    box.className = 'spq';
    box.title = t(tip);
    const label = document.createElement('span');
    label.className = 'spq__name';
    label.textContent = t(name);
    box.append(label,
      button('textbtn textbtn--sm', less, '', () => quickEdit(kind, false)),
      button('textbtn textbtn--sm', more, '', () => quickEdit(kind, true)));
    quick.append(box);
  }

  const tools = document.createElement('div');
  tools.className = 'spbar__view';
  const seg = document.createElement('span');
  seg.className = 'spseg';
  for (const f of FILTERS) {
    const b = button('underlined' + (view.filter === f.key ? ' is-active' : ''), f.label, f.tip, () => {
      view.filter = f.key;
      saveView();
      showParams(system);
    });
    seg.append(b);
  }
  const hints = button('underlined spbar__hints' + (view.hints ? ' is-active' : ''),
    'Пояснения', 'Короткое описание под каждой крутилкой', () => {
      view.hints = !view.hints;
      saveView();
      showParams(system);
    });
  tools.append(seg, hints);
  bar.append(quick, tools);
  return bar;
}

/** Раздел: заголовок сворачивает его, рядом - сколько в нём изменено */
function section(name, index, params) {
  const sec = document.createElement('section');
  const bit = 1 << index;
  sec.className = 'spg' + (view.folded & bit ? ' is-folded' : '');
  const head = document.createElement('button');
  head.type = 'button';
  head.className = 'label spg__head';
  head.textContent = name;
  const changed = params.filter(isChanged).length;
  if (changed) {
    const mark = document.createElement('span');
    mark.className = 'spg__mark';
    mark.textContent = t('изменено: {}').replace('{}', changed);
    head.append(mark);
  }
  head.addEventListener('click', () => {
    view.folded ^= bit;
    sec.classList.toggle('is-folded', Boolean(view.folded & bit));
    saveView();
  });
  const grid = document.createElement('div');
  grid.className = 'spg__grid';
  for (const p of params) grid.append(paramCard(p, { hints: view.hints }));
  sec.append(head, grid);
  return sec;
}

/** Рисует панель параметров выбранной системы */
export async function showParams(system) {
  setSystem(system);
  const expert = pMode === 'expert';
  plist.hidden = expert;
  pfind.hidden = !expert;
  document.getElementById('pexpert').hidden = !expert;
  if (expert) {
    pnote.hidden = true;
    await showExpert(system);
    // Запрос переживает смену системы: ищут обычно одно и то же в разных
    if (pfind.value) filterExpert(pfind.value);
    return;
  }

  const list = await api.particleParams(system);
  if (pSystem !== system) return;              // выбор успел смениться

  // Прокрутка панели остаётся на месте: после правки панель рисуется
  // заново, и прыжок наверх терял крутилку, которую только что тянули
  const scroller = plist.closest('.params');
  const top = scroller ? scroller.scrollTop : 0;
  plist.innerHTML = '';
  pnote.hidden = list.length > 0;
  if (!list.length) return;
  plist.append(toolbar(system));

  // Разделы - в порядке схемы; номер раздела - его бит в свёрнутых
  const groups = new Map();
  for (const p of list) {
    if (!groups.has(p.group)) groups.set(p.group, { name: p.group_name, params: [] });
    if (passes(p)) groups.get(p.group).params.push(p);
  }
  let shown = 0;
  [...groups.values()].forEach((g, i) => {
    if (!g.params.length) return;
    shown += g.params.length;
    plist.append(section(g.name, i, g.params));
  });
  if (!shown) {
    const note = document.createElement('p');
    note.className = 'params__note';
    note.textContent = t(view.filter === 'changed'
      ? 'Эта система не отличается от игры.'
      : 'Под фильтр ничего не подходит.');
    plist.append(note);
  }
  if (scroller) scroller.scrollTop = top;
  // Доступность отмены зависит от ЛЮБОЙ правки, а не только структурной:
  // сюда сходятся и смена системы, и правка параметра (editParam зовёт нас
  // следом). Без этого кнопки «Отменить»/«Вернуть» показывали состояние на
  // момент загрузки файла
  syncHistory();
}

document.querySelector('.params__modes').addEventListener('click', (e) => {
  const b = e.target.closest('[data-pmode]');
  if (!b) return;
  document.querySelectorAll('[data-pmode]')
          .forEach((x) => x.classList.toggle('is-active', x === b));
  setMode(b.dataset.pmode);
  if (pSystem) showParams(pSystem);
});
