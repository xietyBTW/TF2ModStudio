/*
 * Контекстное меню по правой кнопке
 *
 * Список пунктов даёт вызывающий - модуль решает только, где меню встанет и
 * как закроется. Пункт со значением null рисуется разделителем, пункт
 * `{ heading }` - заголовком группы, `hint` у пункта - строкой пояснения под
 * подписью (в длинном меню одной подписи мало, чтобы понять, что выбираешь).
 * Пункт с `sub` раскрывает справа вложенный список при наведении или щелчке:
 * выбор в нём возвращается так же, как из обычного пункта.
 */

// Контекстные меню
// Как в панели приложения: набор пунктов зависит от того, на чём щёлкнули.
// Правая кнопка на системе даёт одно, на модуле - другое, на параметре -
// третье. Разделитель - пункт со значением null

/** Пустой список меню. Popover - ради верхнего слоя: меню зовут и из
 *  модальных окон (редактор VMT -> «Вставить»), а модальный <dialog> лежит
 *  выше любого z-index. `manual` - закрытием ведаем сами (щелчок мимо, Esc) */
function listEl() {
  const el = document.createElement('div');
  el.className = 'menu__list ctx';
  el.hidden = true;
  el.setAttribute('popover', 'manual');
  document.body.append(el);
  return el;
}

const menuEl = listEl();
//: Подменю по уровням: subs[0] раскрывается из главного списка, subs[1] - из
//: него и так далее. Элементы переиспользуются от меню к меню
const subs = [];

function hide(el) {
  if (!el || el.hidden) return;
  if (el.matches(':popover-open')) el.hidePopover();
  el.hidden = true;
}

/** Закрывает подменю начиная с уровня `level` */
function hideSubs(level) {
  for (let i = level; i < subs.length; i++) hide(subs[i]);
}

/** Показывает список в точке, не давая ему уйти за край окна. Одного слоя
 *  мало: всё вне модального окна инертно, и по меню нельзя было бы щёлкнуть -
 *  поэтому на время показа оно переезжает ВНУТРЬ открытого окна */
function showAt(el, x, y, flipX = null) {
  (document.querySelector('dialog:modal') || document.body).append(el);
  el.hidden = false;
  if (el.showPopover && !el.matches(':popover-open')) el.showPopover();
  const box = el.getBoundingClientRect();
  // Подменю справа не помещается - встаёт слева от своего пункта
  if (flipX !== null && x + box.width > innerWidth - 8) x = flipX - box.width;
  el.style.left = Math.max(8, Math.min(x, innerWidth - box.width - 8)) + 'px';
  el.style.top = Math.max(8, Math.min(y, innerHeight - box.height - 8)) + 'px';
}

//: Сколько ждать, пока курсор, похоже, ведут к открытому подменю. Остановился
//: на соседнем пункте дольше - значит, хотел именно его
const AIM_DELAY = 300;

/** Лежит ли точка p в треугольнике abc */
function inTriangle(p, a, b, c) {
  const side = (u, v, w) => (u.x - w.x) * (v.y - w.y) - (v.x - w.x) * (u.y - w.y);
  const d = [side(p, a, b), side(p, b, c), side(p, c, a)];
  return !(d.some((x) => x < 0) && d.some((x) => x > 0));
}

/** Показывает меню в точке события, отдаёт значение пункта или null */
export function contextMenu(e, items) {
  e.preventDefault();
  return new Promise((resolve) => {
    //: Где курсор был при прошлом движении - вершина «безопасного треугольника»
    let lastPt = null;
    //: По уровням: пункт под курсором и отложенное наведение на него
    const hovered = [];
    const timers = [];

    const close = (value) => {
      timers.forEach(clearTimeout);
      hideSubs(0);
      hide(menuEl);
      document.removeEventListener('mousedown', onAway, true);
      document.removeEventListener('keydown', onKey, true);
      document.removeEventListener('mousemove', onMove, true);
      window.removeEventListener('blur', onBlur);
      resolve(value);
    };
    const onMove = (ev) => { lastPt = { x: ev.clientX, y: ev.clientY }; };

    /** Курсор идёт к открытому подменю: «безопасный треугольник» от его
     *  прошлой точки до ближнего края подменю. Ведут наискосок - курсор
     *  задевает соседние пункты, и без этого подменю пропадало под ним.
     *  Вход на пункт браузер шлёт раньше движения, поэтому текущая точка -
     *  из самого события входа, а прошлая - от последнего движения */
    const aiming = (level, ev) => {
      const sub = subs[level];
      if (!sub || sub.hidden || !lastPt) return false;
      const r = sub.getBoundingClientRect();
      const x = r.left >= lastPt.x ? r.left : r.right;
      return inTriangle({ x: ev.clientX, y: ev.clientY }, lastPt,
                        { x, y: r.top - 8 }, { x, y: r.bottom + 8 });
    };

    /** Наведение на пункт уровня level. Пока курсор целится в подменю,
     *  переключение ждёт: дошёл до подменю - отменяется */
    const enter = (level, b, ev, act) => {
      hovered[level] = b;
      clearTimeout(timers[level]);
      if (!aiming(level, ev)) { act(); return; }
      timers[level] = setTimeout(() => { if (hovered[level] === b) act(); }, AIM_DELAY);
    };
    const inside = (t) => menuEl.contains(t) || subs.some((s) => s && s.contains(t));
    const onAway = (ev) => { if (!inside(ev.target)) close(null); };
    // Escape - только меню: иначе он доходил до страницы и заодно прятал панель
    const onKey = (ev) => {
      if (ev.key !== 'Escape') return;
      ev.stopPropagation();
      ev.preventDefault();
      close(null);
    };
    // Щелчок в 3D-превью (оно в iframe) до страницы не доходит, зато уводит
    // с неё фокус
    const onBlur = () => close(null);

    /** Наполняет список пунктами. level - уровень подменю, которое из него
     *  раскрывается */
    const fill = (el, list, level) => {
      el.innerHTML = '';
      for (const item of list) {
        if (!item) {
          const hr = document.createElement('div');
          hr.className = 'ctx__sep';
          el.append(hr);
          continue;
        }
        if (item.heading) {
          const h = document.createElement('div');
          h.className = 'label ctx__head';
          h.textContent = item.heading;
          el.append(h);
          continue;
        }
        const b = document.createElement('button');
        b.className = 'menu__item';
        b.type = 'button';
        b.textContent = item.label;
        if (item.hint) {
          const hint = document.createElement('span');
          hint.className = 'ctx__hint';
          hint.textContent = item.hint;
          b.append(hint);
        }
        b.disabled = Boolean(item.disabled);
        if (item.sub) {
          b.classList.add('ctx__more');
          const open = () => {
            if (b.disabled || b.classList.contains('is-open')) return;
            hideSubs(level);
            el.querySelectorAll('.is-open').forEach((x) => x.classList.remove('is-open'));
            b.classList.add('is-open');
            const sub = subs[level] = subs[level] || listEl();
            // Дошёл до подменю - отложенное переключение больше не нужно
            sub.onmouseenter = () => { clearTimeout(timers[level]); hovered[level] = null; };
            fill(sub, item.sub, level + 1);
            // От конечного места списка, а не от getBoundingClientRect:
            // список ещё доезжает анимацией появления, и подменю вставало
            // на её смещение выше своего пункта
            const left = parseFloat(el.style.left);
            const top = parseFloat(el.style.top) + b.offsetTop - el.scrollTop;
            showAt(sub, left + el.offsetWidth - 1, top, left + 1);
          };
          b.addEventListener('mouseenter', (ev) => enter(level, b, ev, open));
          b.addEventListener('click', open);
        } else {
          // Соседний обычный пункт закрывает раскрытое рядом подменю
          b.addEventListener('mouseenter', (ev) => enter(level, b, ev, () => {
            hideSubs(level);
            el.querySelectorAll('.is-open').forEach((x) => x.classList.remove('is-open'));
          }));
          b.addEventListener('click', () => close(item.value));
        }
        el.append(b);
      }
    };

    hideSubs(0);
    fill(menuEl, items, 0);
    showAt(menuEl, e.clientX, e.clientY);
    document.addEventListener('mousedown', onAway, true);
    document.addEventListener('keydown', onKey, true);
    document.addEventListener('mousemove', onMove, true);
    window.addEventListener('blur', onBlur);
  });
}
