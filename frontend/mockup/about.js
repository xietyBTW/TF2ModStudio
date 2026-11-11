/*
 * Вкладка «О программе»: версия и обновление, связь с автором, отчёт об ошибке
 *
 * Адреса ссылок знает Python (app_links.py): сначала приходят сохранённые
 * вместе с настройками, потом свежие с GitHub
 */

import * as api from './api.js';
import { ask } from './ask.js';
import { notifyApp } from './app-note.js';
import { t } from './i18n.js';

const $ = (id) => document.getElementById(id);

/** Заполняет вкладку. Зовётся после показа окна настроек */
export function showAbout(cfg) {
  $('cfg-version').textContent = 'v' + cfg.version;
  fillLinks(cfg.links || {});
  // Сеть - после показа окна и без await: открытие настроек её не ждёт
  api.appLinks().then(fillLinks).catch(() => {});
  showUpdate();
}

let discordName = '';

function fillLinks(links) {
  for (const key of ['discord', 'steam', 'issues', 'support']) {
    const a = $('cfg-' + key);
    // Без href ссылка прячется (.cfg__link:not([href]) в CSS)
    if (links[key]) a.href = links[key];
    else a.removeAttribute('href');
  }
  discordName = links.discord_name || '';
  $('cfg-discord-name').textContent = discordName;
  $('cfg-discord-copy').hidden = !discordName;
}

/** В буфер, а если WebView его не дал - сказать об этом, а не молчать */
async function copy(text, done) {
  try {
    await navigator.clipboard.writeText(text);
    notifyApp(done);
  } catch {
    notifyApp(t('Буфер обмена недоступен - выделите и скопируйте.'), 'error');
  }
}

$('cfg-discord-copy').addEventListener('click', () => copy(discordName, t('Ник скопирован')));

$('cfg-report').addEventListener('click', async () => {
  const res = await api.reportInfo();
  copy(res.text || '', t('Сведения скопированы'));
});

$('cfg-logdir').addEventListener('click', async () => {
  const res = await api.logFolder();
  if (res.error) notifyApp(res.error, 'error');
});

// Обновление приложения
// Ставит СОБРАННОЕ приложение установщиком из релиза: он умеет закрыть нас,
// заменить файлы и починить ярлыки. Из репозитория обновляются через git -
// тогда Python отвечает can_install: false, и остаётся только ссылка

//: Что делает кнопка обновления прямо сейчас. null - «проверить», после
//: проверки это либо установка, либо открытие страницы релиза. Состояние
//: отдельной переменной, а не в onclick элемента: два обработчика на одной
//: кнопке разъезжаются при первой же правке
let updateAction = null;

/** Показывает предложение обновиться, если оно есть */
function showUpdate(force = false) {
  const note = $('cfg-update-note');
  const btn = $('cfg-update');

  note.hidden = !force;
  note.textContent = force ? t('проверяю…') : '';
  btn.disabled = force;
  btn.textContent = t('Проверить обновления');
  updateAction = null;

  api.updateStatus(force).then((u) => {
    btn.disabled = false;
    note.hidden = false;
    if (!u.checked) {
      note.textContent = t('Не удалось проверить обновления - нет связи с GitHub.');
      return;
    }
    if (!u.available) {
      note.textContent = t('Установлена последняя версия.');
      return;
    }
    note.textContent = t('Доступна версия') + ' ' + u.version + '. '
      + (u.can_install
        ? t('Нажмите «Обновить» - приложение закроется и вернётся уже новым.')
        : t('Скачайте её со страницы релиза.'));
    btn.textContent = u.can_install ? t('Обновить') : t('Открыть страницу релиза');
    updateAction = u.can_install
      ? () => runUpdate(u)
      : () => window.open(u.page_url, '_blank', 'noreferrer');
  }).catch(() => {
    btn.disabled = false;
    note.hidden = false;
    note.textContent = t('Не удалось проверить обновления.');
  });
}

/** Качает установщик и отдаёт ему управление. Приложение после этого закроется */
async function runUpdate(u) {
  const go = await ask({
    title: t('Обновить до') + ' ' + u.version,
    // eslint-disable-next-line max-len - ключ словаря должен быть одним литералом
    text: t('Приложение закроется, установщик заменит его на новую версию и запустит заново. Ваши работы, моды и настройки не тронутся - они хранятся отдельно от папки установки.'),
    ok: t('Обновить'),
  });
  if (!go) return;

  const note = $('cfg-update-note');
  const btn = $('cfg-update');
  note.hidden = false;
  note.textContent = t('Скачиваю установщик…');
  // Скачивание уже идёт, второе нажатие ничего не ускорит
  btn.disabled = true;
  updateAction = null;

  try {
    await api.installUpdate();
  } catch (err) {
    btn.disabled = false;
    note.textContent = t('Обновление не установлено') + ': ' + err.message;
    return;
  }
  watchUpdate();
}

/**
 * Опрашивает ход обновления и пишет его в подпись
 *
 * Опрос, а не поток событий: установщик носит приложение внутри себя, это
 * десятки мегабайт, и всё, что нужно показать, - сколько уже скачано.
 * Заводить ради одной строки подписку не за чем.
 */
function watchUpdate() {
  const note = $('cfg-update-note');
  const btn = $('cfg-update');
  const mb = (bytes) => (bytes / 1048576).toFixed(1);

  const tick = async () => {
    let p;
    try {
      p = await api.updateProgress();
    } catch (err) {
      // Приложение уже закрывается - опрос обрывается, и это норма
      return;
    }
    if (p.state === 'downloading') {
      note.textContent = p.total
        ? t('Скачиваю установщик…') + ' ' + mb(p.done) + ' / ' + mb(p.total) + ' ' + t('МБ')
        : t('Скачиваю установщик…');
      setTimeout(tick, 500);
      return;
    }
    if (p.state === 'launching' || p.state === 'done') {
      note.textContent = t('Установщик запущен, приложение закрывается…');
      return;
    }
    if (p.state === 'error') {
      btn.disabled = false;
      note.textContent = t('Обновление не установлено') + ': ' + (p.error || '');
      return;
    }
    setTimeout(tick, 500);
  };
  tick();
}

$('cfg-update').addEventListener('click', () => {
  // Пока проверки не было - кнопка спрашивает заново, минуя ответ,
  // запомненный на сеанс. После - делает то, что предложила
  if (updateAction) updateAction();
  else showUpdate(true);
});
