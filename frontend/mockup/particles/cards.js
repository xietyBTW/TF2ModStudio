/*
 * Карточки простого режима: одна крутилка - одна карточка
 *
 * Вид карточки задаёт `kind` из схемы (services/simple_params_schema): число,
 * диапазон, цвет, пара цветов, переключатель, выбор, наличие модуля.
 * Раскладкой по разделам и фильтром занимается params.js
 */

import { t } from '../i18n.js';
import { valueControl, rangeControl, colorField, editParam, previewParam } from './fields.js';
import { PACTS } from './actions.js';

/** Равны ли значения с точностью до показанных знаков */
export function sameValue(a, b, decimals = 2) {
  if (Array.isArray(a) && Array.isArray(b)) {
    return a.length === b.length && a.every((x, i) => sameValue(x, b[i], decimals));
  }
  if (typeof a === 'number' && typeof b === 'number') {
    return Math.abs(a - b) < 0.5 * 10 ** -decimals + 1e-9;
  }
  return a === b;
}

/** Отличается ли крутилка от игры. Нет `stock` - сравнивать не с чем */
export function isChanged(param) {
  return 'stock' in param && !sameValue(param.value, param.stock, param.decimals);
}

/** Снять подкраску: частицы рисуются цветами самой текстуры */
function naturalColorsButton() {
  const b = document.createElement('button');
  b.type = 'button';
  b.className = 'textbtn textbtn--sm';
  b.textContent = t('Родные цвета текстуры');
  b.title = t('Убирает подкраску у системы и её дочерних: частицы будут цвета самой текстуры');
  b.addEventListener('click', () => PACTS.natural());
  return b;
}

function el(tag, cls, text) {
  const e = document.createElement(tag);
  if (cls) e.className = cls;
  if (text !== undefined) e.textContent = text;
  return e;
}

/** Переключатель: и для атрибута-флага, и для «есть ли модуль» */
function switchField(on, onEdit) {
  const label = el('label', 'switch');
  const box = el('input');
  box.type = 'checkbox';
  box.checked = Boolean(on);
  box.addEventListener('change', () => onEdit(box.checked));
  label.append(box, el('span', 'switch__knob'));
  return label;
}

/** Выбор из нескольких: кнопки в ряд, а не выпадашка - видно все варианты */
function choiceField(param, value) {
  const row = el('div', 'spchoice');
  for (const c of param.choices) {
    const b = el('button', 'spchoice__b' + (c.value === value ? ' is-active' : ''), c.label);
    b.type = 'button';
    b.addEventListener('click', () => {
      if (c.value !== value) editParam(param, c.value);
    });
    row.append(b);
  }
  return row;
}

/** Числа, тире между концами диапазона и единица - в строку подписи */
function putNumbers(vals, fields, unit) {
  fields.forEach((f, n) => {
    if (n) vals.append(el('span', 'sp__dash', '-'));
    vals.append(f);
  });
  if (unit) vals.append(el('span', 'sp__unit', unit));
}

/** Тело карточки по виду крутилки */
function fillControl(card, vals, param, shown, wake) {
  const live = (v) => { wake(); previewParam(param, v); };
  switch (param.kind) {
    case 'color_pair':
      shown.forEach((c, n) => vals.append(colorField(c, (v) => {
        const pair = shown.map((x) => x.slice());
        pair[n] = v;
        editParam(param, pair);
      })));
      card.append(naturalColorsButton());
      return;
    case 'color':
      vals.append(colorField(shown, (v) => editParam(param, v)));
      return;
    case 'bool':
    case 'module':
      vals.append(switchField(shown, (v) => editParam(param, v)));
      return;
    case 'choice':
      card.append(choiceField(param, param.value));
      return;
    default: {
      const ctl = param.kind === 'range'
        ? rangeControl(shown, param, (v) => editParam(param, v), live)
        : valueControl(shown, param, (v) => editParam(param, v), live);
      putNumbers(vals, ctl.fields, param.unit);
      card.append(ctl.track);
    }
  }
}

/** «Как в игре»: значение из игровой версии файла */
function resetButton(param) {
  const b = el('button', 'textbtn textbtn--sm sp__reset', t('Как в игре'));
  b.type = 'button';
  b.title = t('Вернуть значение из игры');
  b.addEventListener('click', () => editParam(param, param.stock));
  return b;
}

/**
 * Карточка крутилки: подпись и значение одной строкой, под ними дорожка
 *
 * value = null - модуля под параметром нет. Тогда вместо выдуманного числа
 * кнопка «Добавить», а дорожка бледная, но живая: первая правка модуль и
 * создаст. Если создавать нельзя (эмиттеры, рендерер), всё погашено с
 * объяснением
 */
export function paramCard(param, { hints = false } = {}) {
  const card = el('div', 'sp');
  card.dataset.key = param.key;
  card.title = param.hint || '';
  const head = el('div', 'sp__head');
  const name = el('span', 'sp__name', param.name);
  const vals = el('span', 'sp__vals');
  head.append(name, vals);
  card.append(head);
  if (hints && param.hint) card.append(el('p', 'sp__hint', param.hint));

  const shown = param.value === null ? param.placeholder : param.value;
  const empty = param.value === null;
  const dead = empty && !param.creatable;
  const wake = () => card.classList.remove('is-empty');
  fillControl(card, vals, param, shown, wake);

  if (isChanged(param)) {
    card.classList.add('is-changed');
    name.title = t('Отличается от игры');
    if (param.stock !== null && param.stock !== undefined) head.insertBefore(resetButton(param), vals);
  }
  if (dead) {
    card.classList.add('is-dead');
    card.querySelectorAll('input, button').forEach((i) => { i.disabled = true; });
    vals.append(el('span', 'sp__none', t('Нет в системе')));
    card.title = t('В этой системе нет модуля для этого параметра. Отсюда его не '
                   + 'добавить: второй эмиттер или рендерер задвоил бы эффект.');
  } else if (empty) {
    card.classList.add('is-empty');
    const add = el('button', 'textbtn textbtn--sm sp__add', t('Добавить'));
    add.type = 'button';
    add.addEventListener('click', () => editParam(param, shown));
    vals.append(add);
  }
  return card;
}
