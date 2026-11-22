/*
 * «Показать снова» из настроек: дойти до места тура и начать его там
 *
 * Тур живёт в своём месте (режим частей, War Paint, раздел звуков), и раньше
 * после сброса он ждал, пока человек сам туда придёт, - а куда, было не
 * понять. Здесь путь до места: те же кнопки, что нажал бы человек. Оружие -
 * то, что уже в кадре, а если его нет, случайное стоковое, у которого в игре
 * есть War Paint. Подгонку открыть нельзя без своей модели человека - тогда
 * тур ждёт её, а настройки говорят об этом
 *
 * Сам tour.js об устройстве модулей не знает и знать не должен - всё про
 * «куда нажать» лежит здесь
 */

import * as api from './api.js';
import { goSection, openItem, sel } from './catalog.js';
import { resetTour, startTour } from './tour.js';
import { say } from './stage.js';

const $ = (s) => document.querySelector(s);
const shown = (el) => Boolean(el) && el.getClientRects().length > 0
  && getComputedStyle(el).visibility !== 'hidden';

//: Стоковое оружие, у которого в игре есть War Paint (ключи каталога)
const WAR_PAINT_WEAPONS = [
  'c_scattergun', 'c_pistol', 'c_rocketlauncher', 'c_shotgun', 'c_flamethrower',
  'c_grenadelauncher', 'c_minigun', 'c_wrench', 'c_medigun', 'c_sniperrifle',
  'c_smg', 'c_revolver', 'c_knife',
];

//: Сколько ждать модель: первый разбор оружия без кэша - это секунды
const MODEL_WAIT = 45000;

/** Ждёт, пока test() станет правдой. false - не дождались */
async function until(test, ms = 8000) {
  const end = Date.now() + ms;
  while (Date.now() < end) {
    if (test()) return true;
    await new Promise((r) => setTimeout(r, 150));
  }
  return test();
}

/** Оружие в кадре: то, что уже открыто, иначе случайное с War Paint */
async function weapon() {
  if (sel.section === 'weapons' && shown($('#warpaint'))) return true;
  await goSection('weapons');
  const items = await api.items({ category: 'weapon' });
  const pool = items.filter((it) => WAR_PAINT_WEAPONS.includes(it.key));
  if (!pool.length) return false;
  await openItem(pool[Math.floor(Math.random() * pool.length)]);
  return until(() => shown($('#warpaint')), MODEL_WAIT);
}

async function warpaint() {
  if (!await weapon()) return false;
  if (!shown($('#warpaintpanel'))) $('#warpaint').click();
  return until(() => shown($('#warpaintpanel')));
}

//: Путь до места каждого тура. true - место на экране, тур можно начинать
const ROUTES = {
  main: async () => { await goSection('weapons'); return true; },
  hats: async () => { await goSection('hats'); return true; },
  particles: async () => { await goSection('particles'); return true; },
  sounds: async () => {
    await goSection('sounds');
    return until(() => shown($('#snd-list')));
  },
  parts: async () => {
    if (!await weapon()) return false;
    if ($('#partsbar').hidden) $('#parts').click();
    return until(() => shown($('#partspaint')));
  },
  warpaint,
  warpaintLayout: async () => {
    if (!await warpaint()) return false;
    // «Настроить» есть, когда выбрана раскраска
    if (!shown($('.wpanel__tune'))) {
      await until(() => Boolean($('.wpanel__list button .wpanel__name')));
      $('.wpanel__list button .wpanel__name')?.closest('button').click();
    }
    if (!await until(() => shown($('.wpanel__tune')))) return false;
    $('.wpanel__tune').click();
    return until(() => shown($('.wlay__units')) && Boolean($('.wlay__unit')));
  },
  fit: async () => {
    if (!shown($('#fitpanel'))) $('#fitbtn').click();
    return until(() => shown($('#fitpanel')));
  },
};

/** Можно ли дойти до места тура прямо сейчас. Подгонке нужна своя модель:
 *  без неё значка подгонки нет, и вести некуда */
export function canGo(name) {
  return name !== 'fit' || shown($('#fitbtn')) || shown($('#fitpanel'));
}

/**
 * Тур заново: дойти до его места и начать. Не дошли (модель не открылась) -
 * тур остаётся неотмеченным и начнётся сам, когда место появится
 */
export async function showTourAgain(name) {
  resetTour(name);
  const route = ROUTES[name];
  if (!route) return;
  say('Готовлю обучение…');
  let there = false;
  try {
    there = await route();
  } finally {
    say('');
  }
  if (there) startTour(name);
}
