/*
 * Объединение модов в один VPK - одно окно вместо цепочки вопросов
 *
 * Моды папки экспорта списком: отметка, размер, что внутри, порядок. Порядок -
 * это приоритет: если два мода кладут файл по одному пути, остаётся версия
 * того, что выше. Пересечения считает Python (merge_plan) и показывает
 * окно сразу, пока человек отмечает, - а не вопросом после всего.
 */

import * as api from './api.js';
import { t } from './i18n.js';
import { say } from './stage.js';
import { notifyApp } from './app-note.js';
import { fileSize } from './util.js';

const dlg = document.getElementById('mergedlg');
const listEl = dlg.querySelector('.mergepick__list');
const conflictsEl = dlg.querySelector('.mergepick__conflicts');
const fileEl = dlg.querySelector('.mergepick__file');
const countEl = dlg.querySelector('.mergepick__count');
const okBtn = dlg.querySelector('.ask__ok');
const cancelBtn = dlg.querySelector('.ask__cancel');

//: Строки окна в показанном порядке: {mod, on}
let rows = [];
let checkSeq = 0;
let checkTimer = null;

/** Открывает окно объединения. Само запускает сборку по «Объединить» */
export async function mergeMods() {
  const mods = await api.mergeCandidates();
  if (mods.length < 2) {
    notifyApp(mods.length ? 'Для объединения нужно хотя бы два собранных мода'
                          : 'В папке экспорта нет собранных модов', 'info');
    return;
  }
  rows = mods.map((mod) => ({ mod, on: false }));
  fileEl.value = 'merged_mod.vpk';
  render();
  dlg.showModal();
}

function chosen() {
  return rows.filter((r) => r.on).map((r) => r.mod.name);
}

function render() {
  listEl.innerHTML = '';
  rows.forEach((row, i) => listEl.appendChild(rowEl(row, i)));
  const n = chosen().length;
  countEl.textContent = n ? t('Отмечено: {}').replace('{}', n) : '';
  okBtn.disabled = n < 2 || !fileEl.value.trim();
  scheduleCheck();
}

/** Строка мода: отметка, имя и размер, что внутри, стрелки порядка */
function rowEl(row, i) {
  const el = document.createElement('div');
  el.className = 'mergepick__row' + (row.on ? ' is-active' : '');
  el.setAttribute('role', 'listitem');

  const pick = document.createElement('button');
  pick.type = 'button';
  pick.className = 'mergepick__pick';
  pick.setAttribute('aria-pressed', String(row.on));
  const name = document.createElement('span');
  name.className = 'mergepick__mod';
  name.textContent = row.mod.name;
  const meta = document.createElement('span');
  meta.className = 'mono mergepick__meta';
  meta.textContent = fileSize(row.mod.size);
  const items = document.createElement('span');
  items.className = 'mergepick__items';
  items.textContent = describe(row.mod);
  pick.append(name, meta, items);
  pick.addEventListener('click', () => { row.on = !row.on; render(); });

  const up = arrow('↑', t('Выше - главнее'), i > 0, () => move(i, -1));
  const down = arrow('↓', t('Ниже'), i < rows.length - 1, () => move(i, 1));
  el.append(pick, up, down);
  return el;
}

function arrow(text, title, enabled, onClick) {
  const b = document.createElement('button');
  b.type = 'button';
  b.className = 'textbtn textbtn--sm mergepick__move';
  b.textContent = text;
  b.title = title;
  b.disabled = !enabled;
  b.addEventListener('click', onClick);
  return b;
}

function move(i, step) {
  const j = i + step;
  [rows[i], rows[j]] = [rows[j], rows[i]];
  render();
}

/** Что в моде - словами: первые предметы и сколько ещё */
function describe(mod) {
  const items = mod.items || [];
  if (!items.length) return t('{} файлов').replace('{}', mod.files || 0);
  const more = mod.more ? ` +${mod.more}` : '';
  return items.join(', ') + more;
}

/** Пересечения отмеченных - чуть погодя: щёлкают подряд, а читать VPK
 *  на каждый щелчок незачем */
function scheduleCheck() {
  clearTimeout(checkTimer);
  const picked = chosen();
  if (picked.length < 2) { showConflicts(null); return; }
  checkTimer = setTimeout(async () => {
    const seq = ++checkSeq;
    const res = await api.mergeCheck(picked);
    if (seq === checkSeq) showConflicts(res.conflicts || []);
  }, 200);
}

function showConflicts(list) {
  conflictsEl.innerHTML = '';
  conflictsEl.hidden = list === null;
  if (list === null) return;
  conflictsEl.classList.toggle('is-clear', !list.length);
  if (!list.length) {
    conflictsEl.textContent = t('Пересечений нет - войдёт всё');
    return;
  }
  const head = document.createElement('p');
  head.className = 'label mergepick__warn';
  head.textContent = t('Моды меняют одно и то же');
  conflictsEl.appendChild(head);
  for (const c of list) {
    const p = document.createElement('p');
    p.className = 'mergepick__conflict';
    const what = document.createElement('b');
    what.textContent = c.item;
    const how = document.createElement('span');
    how.textContent = c.files
      ? t('{}: останется из {}').replace('{}', c.mods.join(', ')).replace('{}', c.winner)
      : t('{}: модель лежит по разным путям, в игре будет видна одна')
          .replace('{}', c.mods.join(', '));
    p.append(what, ' - ', how);
    conflictsEl.appendChild(p);
  }
}

fileEl.addEventListener('input', () => {
  okBtn.disabled = chosen().length < 2 || !fileEl.value.trim();
});

cancelBtn.addEventListener('click', () => dlg.close());

okBtn.addEventListener('click', async () => {
  const picked = chosen();
  const res = await api.mergeVpk(picked, fileEl.value.trim(), true);
  if (res.error) { notifyApp(res.error, 'error'); return; }
  dlg.close();
  say('Объединение…');
});
