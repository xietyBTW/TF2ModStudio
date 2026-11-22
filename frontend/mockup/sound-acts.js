/*
 * Действия строки звука: значки с подсказками и отклик на скачивание
 *
 * Скачанный звук раньше подтверждался мелкой подписью в подвале, и понять,
 * скачался ли он, было нельзя. Теперь значок на месте становится галочкой, а
 * над пультом всплывает итог с «Показать в папке»
 */

import * as api from './api.js';

const toast = document.getElementById('snd-toast');
const toastText = document.getElementById('snd-toast-text');
const toastOpen = document.getElementById('snd-toast-open');

//: Значки действий строки: SVG в разметке, цвет от текста, как у плеера
const ACT_ICON = {
  play: '<path d="M8 5.5v13l11-6.5z" fill="currentColor"/>',
  orig: '<path d="M4.5 12a7.5 7.5 0 1 0 2.2-5.3"/><path d="M4.5 4v4h4"/>',
  save: '<path d="M12 4v11"/><path d="m7 10 5 5 5-5"/><path d="M5 20h14"/>',
  own: '<path d="M12 15V4"/><path d="m7 9 5-5 5 5"/><path d="M5 20h14"/>',
  drop: '<path d="m7 7 10 10M17 7 7 17"/>',
};
//: Подсказки к значкам. Без подписи значок «стрелка вверх» мог бы значить
//: что угодно, поэтому подсказка говорит действие целиком
const ACT_TIP = {
  play: 'Прослушать', orig: 'Прослушать оригинал', save: 'Скачать',
  own: 'Заменить своим файлом', drop: 'Убрать свой файл',
};

/** Кнопка-значок действия. attr - data-act у строки, data-file у файла */
export function actButton(attr, act, hidden = false) {
  return `<button class="snd__ic" type="button" ${attr}="${act}" title="${ACT_TIP[act]}"
    aria-label="${ACT_TIP[act]}"${hidden ? ' hidden' : ''}><svg viewBox="0 0 24 24"
    aria-hidden="true" fill="none" stroke="currentColor" stroke-width="1.8"
    stroke-linecap="round" stroke-linejoin="round">${ACT_ICON[act]}</svg></button>`;
}

/** Кладёт игровой звук в папку экспорта: чтобы переделать, его надо
 *  достать. wave - один файл записи, пусто - все: у записи бывает несколько
 *  файлов, игра берёт случайный, и переделывать обычно надо все */
export async function saveSound(row, btn, wave = '') {
  const res = await api.saveSound(row.name, wave);
  if (res.error) {
    showToast(res.error, '', true);
    return;
  }
  markSaved(btn);
  showToast(res.files > 1 ? `Скачано файлов: ${res.files}` : `Скачано: ${res.name}`,
            res.path);
}

/** Значок скачивания на пару секунд становится галочкой - там же, куда
 *  нажимали, без поиска глазами по экрану */
function markSaved(btn) {
  const svg = btn?.querySelector('svg');
  if (!svg) return;
  svg.innerHTML = '<path d="m5 12.5 4.5 4.5L19 7.5"/>';
  btn.classList.add('is-done');
  clearTimeout(btn.doneTimer);
  btn.doneTimer = setTimeout(() => {
    svg.innerHTML = ACT_ICON.save;
    btn.classList.remove('is-done');
  }, 2500);
}

//: Сколько держать уведомление. Наведение держит его, пока нужно
const TOAST_KEEP = 6000;
let toastTimer = null;

/** Уведомление над пультом. path - что показать в проводнике */
function showToast(text, path = '', error = false) {
  toastText.textContent = text;
  toast.classList.toggle('is-error', error);
  toastOpen.hidden = !path;
  toast.dataset.path = path;
  toast.classList.remove('is-on');
  void toast.offsetWidth;          // новое сообщение заново всплывает
  toast.classList.add('is-on');
  hideToastLater(TOAST_KEEP);
}

function hideToastLater(ms) {
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => toast.classList.remove('is-on'), ms);
}

toastOpen.addEventListener('click', async () => {
  const res = await api.revealExportFile(toast.dataset.path || '');
  if (res.error) showToast(res.error, '', true);
});
toast.addEventListener('mouseenter', () => clearTimeout(toastTimer));
toast.addEventListener('mouseleave', () => hideToastLater(2500));
