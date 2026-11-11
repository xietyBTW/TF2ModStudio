/*
 * Колонка слоёв в окне посадки картинки: выбор и перестановка перетаскиванием
 *
 * Стопку держит само окно (place.js), здесь только её показ и жесты
 */

import * as api from './api.js';
import { t } from './i18n.js';

/**
 * Колонка картинок части
 *
 * Строки лежат так же, как картинки: верхняя - поверх. Щелчок выбирает
 * слой, а перетаскивание переставляет - порядок в списке и есть порядок
 * наложения. Тащим сами, без drag-and-drop браузера: тому нужен призрак и
 * долгое нажатие на тачпаде, а здесь строка едет за курсором сразу, соседи
 * уступают место плавно, и отпущенная доезжает до своей щели.
 *
 * Строится заново после каждой правки стопки: `pick(n)` и `move(from, to)`
 * меняют её в окне, номера - снизу вверх; `replace`, `copy`, `drop` -
 * действия над выбранным слоем
 */
export function showLayers(state, on, { pick, move, replace, copy, drop }) {
  const list = document.getElementById('place-list');
  list.replaceChildren();
  const count = state.layers.length;
  document.getElementById('place-count').textContent = String(count);
  //: Порядок показа -> номер слоя в стопке (стопка считается снизу вверх)
  const shown = state.layers.map((_, i) => i).reverse();
  const rows = shown.map((li, di) => {
    const { spec } = state.layers[li];
    // Строка - не кнопка: внутри неё свои кнопки, а кнопка в кнопке
    // недопустима. Выбор - настоящая кнопка на всю ширину, кроме действий
    const row = document.createElement('div');
    row.className = 'place__layer' + (li === state.sel ? ' is-active' : '');
    const pickBtn = document.createElement('button');
    pickBtn.type = 'button';
    pickBtn.className = 'place__pick';
    pickBtn.innerHTML = '<span class="place__grip" aria-hidden="true"></span>'
      + '<span class="place__thumb"><img alt=""></span>'
      + '<span class="place__meta"><span class="place__name mono"></span>'
      + '<span class="place__pos"></span></span>';
    pickBtn.querySelector('img').src = api.fileUrl(spec.path);
    const name = pickBtn.querySelector('.place__name');
    name.textContent = String(spec.path).split(/[\\/]/).pop();
    name.title = name.textContent;
    // Где лежит и как вписан - отдельными словами: так их переводит словарь
    const pos = pickBtn.querySelector('.place__pos');
    const where = count === 1 ? '' : di === 0 ? 'поверх' : di === count - 1 ? 'внизу' : '';
    for (const word of [where, FIT_NAMES[spec.fit]]) {
      if (!word) continue;
      const span = document.createElement('span');
      span.textContent = word;
      pos.append(span);
    }
    row.append(pickBtn);
    if (li === state.sel) row.append(rowActions({ replace, copy, drop }));
    return row;
  });
  list.append(...rows);

  //: Длительность из темы: при выключенной анимации - ноль, и ждать нечего
  const dur = parseFloat(getComputedStyle(document.documentElement)
    .getPropertyValue('--dur')) || 0;
  //: Шаг между строками - расстояние между их верхами, вместе с зазором
  const pitch = () => (rows.length > 1
    ? rows[1].offsetTop - rows[0].offsetTop : rows[0].offsetHeight);

  let drag = null;
  rows.forEach((row, di) => {
    // Щелчок ловим на строке: строку держит захват указателя, и щелчок
    // приходит ей, а не кнопке выбора
    on(row, 'click', (e) => {
      if (e.target.closest('.place__rowacts')) return;
      // После перетаскивания браузер шлёт и щелчок - он не выбор
      if (row.dataset.dragged) { delete row.dataset.dragged; return; }
      pick(shown[di]);
    });
    on(row, 'pointerdown', (e) => {
      if (e.button !== 0 || rows.length < 2 || e.target.closest('.place__rowacts')) return;
      drag = { di, y0: e.clientY, moved: false, target: di };
      row.setPointerCapture(e.pointerId);
    });
    on(row, 'pointermove', (e) => {
      if (!drag || drag.di !== di) return;
      const dy = e.clientY - drag.y0;
      // Порог: щелчок с дрожью руки - всё ещё щелчок
      if (!drag.moved) {
        if (Math.abs(dy) < 4) return;
        drag.moved = true;
        row.dataset.dragged = '1';
        row.classList.add('is-dragging');
        list.classList.add('is-sorting');
      }
      const h = pitch();
      row.style.transform = `translateY(${dy}px) scale(1.02)`;
      const target = Math.max(0, Math.min(rows.length - 1, Math.round(di + dy / h)));
      if (target === drag.target) return;
      drag.target = target;
      // Соседи между старым и новым местом сдвигаются на одну строку
      rows.forEach((other, oi) => {
        if (other === row) return;
        let shift = 0;
        if (di < target && oi > di && oi <= target) shift = -h;
        else if (di > target && oi >= target && oi < di) shift = h;
        other.style.transform = shift ? `translateY(${shift}px)` : '';
      });
    });
    const finish = (e) => {
      if (!drag || drag.di !== di) return;
      const { target, moved } = drag;
      drag = null;
      if (row.hasPointerCapture(e.pointerId)) row.releasePointerCapture(e.pointerId);
      if (!moved) return;
      // Довести строку до щели плавно - и только потом перестроить список:
      // он встанет уже на том же месте, и глазу не за что зацепиться
      row.classList.remove('is-dragging');
      list.classList.remove('is-sorting');
      row.classList.add('is-settling');
      row.style.transform = `translateY(${(target - di) * pitch()}px)`;
      setTimeout(() => {
        if (target !== di) { move(shown[di], shown[target]); return; }
        rows.forEach((r) => { r.style.transform = ''; r.classList.remove('is-settling'); });
      }, dur);
    };
    on(row, 'pointerup', finish);
    on(row, 'pointercancel', finish);
  });
}

//: Подписи вписывания на строке слоя - те же слова, что на кнопках
const FIT_NAMES = { contain: 'Целиком', cover: 'Заполнить', stretch: 'Растянуть' };

//: Значки действий: волосяная линия, как у остальных значков окна
const ICONS = {
  replace: '<path d="M3 5h9l-2.5-2.5M13 11H4l2.5 2.5"/>',
  copy: '<path d="M5 5h8v9H5z"/><path d="M3 11V2h8"/>',
  drop: '<path d="M3 4h10M6 4V2.5h4V4M4.5 4l.7 9.5h5.6l.7-9.5"/>',
};

/** Действия над выбранным слоем - прямо на его строке */
function rowActions(handlers) {
  const box = document.createElement('div');
  box.className = 'place__rowacts';
  const labels = {
    replace: t('Заменить файл, посадка останется'),
    copy: t('Скопировать с посадкой (Ctrl+C)'),
    drop: t('Убрать слой'),
  };
  for (const key of ['replace', 'copy', 'drop']) {
    const b = document.createElement('button');
    b.type = 'button';
    b.className = 'ptools__btn';
    b.title = labels[key];
    b.setAttribute('aria-label', labels[key]);
    b.innerHTML = '<svg viewBox="0 0 16 16" aria-hidden="true">' + ICONS[key] + '</svg>';
    b.addEventListener('click', () => handlers[key]());
    box.append(b);
  }
  return box;
}
