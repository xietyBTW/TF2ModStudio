/*
 * Фильтры каталога: «Класс  Scout ▾» текстом и список под ним
 *
 * Ряды строит catalog.js как раньше. Здесь у ряда появляется кнопка, а его
 * варианты становятся списком под ней. На кнопке видно выбранное, поэтому
 * отдельная сводка фильтров над сеткой не нужна
 */

import { t } from './i18n.js';

const drops = [];
//: С какой длины в списке есть поиск: файлов PCF 136, коллекций около
//: сорока, листать их глазами долго. Короткие списки видны целиком
const SEARCH_FROM = 12;

function closeAll(except = null) {
  for (const d of drops) {
    if (d === except) continue;
    d.row.classList.remove('is-open');
    d.btn.setAttribute('aria-expanded', 'false');
  }
}

/** Делает из ряда выпадашку. multi - ряд переключателей: он не закрывается
 *  после щелчка, на кнопке перечислено включённое. У обычного ряда крестик
 *  выбирает первый вариант - «Все».
 *  select - ряд поверх скрытого <select>: варианты берутся из него при
 *  открытии, выбор ставит значение и шлёт change, как сделал бы сам select */
export function addDrop(row, { label, multi = false, select = null }) {
  const btn = document.createElement('button');
  btn.type = 'button';
  btn.className = 'fdrop';
  btn.setAttribute('aria-expanded', 'false');
  btn.innerHTML = '<span class="fdrop__label"></span><span class="fdrop__name"></span>';
  btn.querySelector('.fdrop__label').textContent = label;
  const d = { row, btn, label, multi, select, x: null };

  if (!multi) {
    const x = document.createElement('span');
    x.className = 'fdrop__x';
    x.title = 'Убрать';
    x.textContent = '×';
    x.hidden = true;
    x.addEventListener('click', (e) => {
      e.stopPropagation();
      closeAll();
      if (select) pickOption(d, 0);
      else row.querySelector('.catalog__opts .underlined')?.click();
    });
    btn.append(x);
    d.x = x;
  }

  btn.addEventListener('click', () => {
    const open = !row.classList.contains('is-open');
    if (open && select) fillFromSelect(d);
    closeAll(d);
    row.classList.toggle('is-open', open);
    btn.setAttribute('aria-expanded', String(open));
  });
  // Один выбор - список закрывается сам, как обычный select
  if (!multi) {
    row.addEventListener('click', (e) => {
      if (e.target.closest('.catalog__opts .underlined')) closeAll();
    });
  }
  row.prepend(btn);
  drops.push(d);
  refreshDrop(d);
}

/** Варианты select списком. Строится при открытии: коллекции и файлы
 *  меняются от запроса, держать вторую копию в синхроне незачем */
function fillFromSelect(d) {
  const box = d.row.querySelector('.catalog__opts');
  const buttons = [...d.select.options].map((o, i) => {
    const b = document.createElement('button');
    b.type = 'button';
    b.className = 'underlined' + (i === d.select.selectedIndex ? ' is-active' : '');
    b.textContent = o.dataset.name || o.text;
    if (o.dataset.count) {
      const n = document.createElement('i');
      n.className = 'underlined__n mono';
      n.textContent = o.dataset.count;
      b.append(n);
    }
    b.dataset.q = b.textContent.toLowerCase();
    b.addEventListener('click', () => pickOption(d, i));
    return b;
  });
  if (buttons.length <= SEARCH_FROM) { box.replaceChildren(...buttons); return; }
  box.replaceChildren(searchBox(buttons), ...buttons);
}

/** Поле над списком: сужает его по мере набора, Enter берёт первый */
function searchBox(buttons) {
  const wrap = document.createElement('div');
  wrap.className = 'fdrop__find';
  const input = document.createElement('input');
  input.type = 'search';
  input.className = 'fdrop__search';
  input.placeholder = t('Поиск');
  const empty = document.createElement('p');
  empty.className = 'fdrop__empty';
  empty.textContent = 'Ничего не найдено';
  empty.hidden = true;
  input.addEventListener('input', () => {
    const words = input.value.toLowerCase().split(/\s+/).filter(Boolean);
    let any = false;
    for (const b of buttons) {
      const typos = matchTypos(b.dataset.q, words);
      b.hidden = typos < 0;
      // Найденное с опечаткой - под найденным точно
      b.style.order = typos > 0 ? 1 : 0;
      any ||= !b.hidden;
    }
    empty.hidden = any;
  });
  input.addEventListener('keydown', (e) => {
    if (e.key !== 'Enter') return;
    const shown = buttons.filter((b) => !b.hidden);
    (shown.find((b) => b.style.order !== '1') || shown[0])?.click();
  });
  // Список ещё не показан - фокус после кадра, иначе браузер его не примет
  requestAnimationFrame(() => input.focus());
  wrap.append(input, empty);
  return wrap;
}

/*
 * Опечатки - тем же правилом, что поиск каталога в Python (text_search.py):
 * до трёх букв точно, с четырёх одна опечатка, с восьми две, и ищется она в
 * начале слов. Правило менять в обоих местах
 */
const typoBudget = (w) => (w.length < 4 ? 0 : w.length < 8 ? 1 : 2);

/** Правок до лучшего начала слова (Дамерау-Левенштейн), больше limit - limit + 1 */
function prefixTypos(q, w, limit) {
  const n = q.length;
  const m = Math.min(w.length, n + limit);
  let before = [];
  let prev = Array.from({ length: m + 1 }, (_, j) => j);
  for (let i = 1; i <= n; i += 1) {
    const cur = [i];
    for (let j = 1; j <= m; j += 1) {
      let best = Math.min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (q[i - 1] !== w[j - 1]));
      if (i > 1 && j > 1 && q[i - 1] === w[j - 2] && q[i - 2] === w[j - 1]) {
        best = Math.min(best, before[j - 2] + 1);
      }
      cur.push(best);
    }
    if (Math.min(...cur) > limit) return limit + 1;
    [before, prev] = [prev, cur];
  }
  return Math.min(...prev);
}

/** -1 - мимо, иначе сколько слов запроса нашлось только с опечаткой */
function matchTypos(raw, words) {
  const text = raw.replace(/ё/g, 'е');
  const parts = text.split(/[^0-9a-zа-я]+/).filter(Boolean);
  let typos = 0;
  for (const word of words) {
    const q = word.replace(/ё/g, 'е');
    if (text.includes(q)) continue;
    const limit = typoBudget(q);
    if (limit && parts.some((w) => prefixTypos(q, w, limit) <= limit)) {
      typos += 1;
      continue;
    }
    return -1;
  }
  return typos;
}

function pickOption(d, i) {
  closeAll();
  if (d.select.selectedIndex === i) return;
  d.select.selectedIndex = i;
  d.select.dispatchEvent(new Event('change'));
  refreshDrop(d);
}

function refreshDrop(d) {
  if (d.select) {
    const o = d.select.selectedOptions[0];
    const name = o ? (o.dataset.name || o.text) : '';
    d.btn.querySelector('.fdrop__name').textContent = name;
    // Имена коллекций в игре сами начинаются со слова «Коллекция»
    const labelEl = d.btn.querySelector('.fdrop__label');
    labelEl.hidden = name.toLowerCase().startsWith(labelEl.textContent.toLowerCase());
    d.btn.classList.toggle('is-set', d.select.selectedIndex > 0);
    if (d.x) d.x.hidden = !(d.select.selectedIndex > 0);
    return;
  }
  const opts = [...d.row.querySelectorAll('.catalog__opts .underlined')];
  const on = opts.filter((b) => b.classList.contains('is-active'));
  const nameOf = (b) => b.firstChild.textContent;
  let name;
  let set;
  if (d.multi) {
    set = on.length > 0;
    name = set ? on.map(nameOf).join(', ') : 'нет';
  } else {
    // Первый вариант - «Все»: он выбран, значит фильтра нет
    set = on.length > 0 && on[0] !== opts[0];
    name = on[0] ? nameOf(on[0]) : (opts[0] ? nameOf(opts[0]) : '');
  }
  d.btn.querySelector('.fdrop__name').textContent = name;
  d.btn.classList.toggle('is-set', set);
  if (d.x) d.x.hidden = !set;
}

/** Подписи кнопок по текущему выбору. Зовётся после каждой перерисовки рядов */
export function refreshDrops() { drops.forEach(refreshDrop); }

/** Закрывает открытый список: смена раздела не должна оставлять его висеть */
export function closeDrops() { closeAll(); }

// Щелчок мимо закрывает. Решаем на pointerdown: ряд перерисовывается на
// каждый выбор, и к click узла под курсором уже нет
document.addEventListener('pointerdown', (e) => {
  if (!drops.some((d) => d.row.classList.contains('is-open'))) return;
  if (drops.some((d) => d.row.contains(e.target))) return;
  closeAll();
});

// Esc сначала закрывает список, каталог остаётся открытым
document.addEventListener('keydown', (e) => {
  if (e.key !== 'Escape' || !drops.some((d) => d.row.classList.contains('is-open'))) return;
  e.stopPropagation();
  closeAll();
}, true);
