/*
 * Граница между половинами работы: её тянут мышью
 *
 * В режиме «Вместе» слева текстуры, справа модель (или эффект), и делили они
 * ширину поровну. Пополам подходит не всякой работе: у развёртки с четырьмя
 * материалами карточки жмутся в колонку, пока половина модели стоит пустой,
 * а модель, наоборот, разглядывают крупно
 *
 * Тянут за ручку - элемент на весь зазор сетки (`gap`), в котором и так
 * никого нет. Вид и наведение у неё в style.css (`.work__grip`), видна она
 * только там, где половины стоят рядом
 *
 * Доля левой половины живёт в `--split` (единицы `fr`, поэтому пропорция
 * переживает изменение размера окна), а между запусками - в общем конфиге
 * (`split_percent`), как ширина панели частиц (см. panel-resize.js).
 */

import * as api from './api.js';

const work = document.querySelector('.work');
const flat = work.querySelector('.half--flat');
const model = work.querySelector('.half--model');

//: Уже этого половина бесполезна: в ней не помещается ни карточка, ни модель
const MIN = 15;
const MAX = 85;

const grip = document.createElement('div');
grip.className = 'work__grip';
grip.setAttribute('aria-hidden', 'true');
work.append(grip);

/** Ширина зазора сетки. Меряем, а не берём константой: на разных порогах своя */
const gap = () => model.getBoundingClientRect().left - flat.getBoundingClientRect().right;

/** Ставит долю левой половины в процентах. 0 - границу не трогали, поровну */
export function setSplit(percent) {
  const p = Number(percent) || 0;
  if (!p) { work.style.removeProperty('--split'); return; }
  const share = Math.min(MAX, Math.max(MIN, p));
  // Левая колонка получает столько же долей, во сколько раз она больше правой
  work.style.setProperty('--split', `${share / (100 - share)}fr`);
}

/** Доля левой половины под курсором, в процентах */
function shareAt(clientX) {
  const box = work.getBoundingClientRect();
  const g = gap();
  // Курсор держит СЕРЕДИНУ зазора, поэтому половина зазора вычитается: иначе
  // граница уезжала бы от него на 15 точек
  const left = clientX - box.left - g / 2;
  return Math.round((left / (box.width - g)) * 100);
}

// Пока тянут, мышь захвачена ручкой: события идут ей, даже когда курсор над
// кадром модели, а полоска горит классом, а не наведением
grip.addEventListener('pointerdown', (e) => {
  if (e.button !== 0) return;
  grip.setPointerCapture(e.pointerId);
  grip.classList.add('is-drag');
  e.preventDefault();               // иначе тянется выделение текста
});

grip.addEventListener('pointermove', (e) => {
  if (!grip.classList.contains('is-drag')) return;
  setSplit(Math.min(MAX, Math.max(MIN, shareAt(e.clientX))));
});

for (const done of ['pointerup', 'pointercancel']) {
  grip.addEventListener(done, (e) => {
    if (!grip.classList.contains('is-drag')) return;
    grip.classList.remove('is-drag');
    // Пишем на ОТПУСКАНИИ: перетаскивание даёт сотню событий, и конфиг
    // переписывался бы сотню раз на одно движение
    api.setUiState('split_percent',
                   Math.min(MAX, Math.max(MIN, shareAt(e.clientX))));
  });
}
