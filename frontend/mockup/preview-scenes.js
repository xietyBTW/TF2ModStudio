/*
 * Сцены кадра: сам предмет, вид от первого лица, насмешка, шапка на
 * персонаже, спец-режимы (крит, эффект смерти) и небо
 *
 * Вид от первого лица и насмешка - не ракурсы, а собранные сцены: их ставит
 * отдельный воркер, и снять их обязан тот же, кто поставил.
 */

import * as api from './api.js';
import { t } from './i18n.js';
import { say, sayInfo, sayError, sayBusy, viewer, withViewer } from './stage.js';
import { root, work } from './layout.js';
import { suspendParts, resumeParts } from './parts.js';
import { flushFitSave } from './custom-model.js';
import { applyView, lastModel, showModel, refreshView } from './preview.js';
import { cardTitles, showMaterials } from './preview-frames.js';
import { still } from './motion.js';
import { contextMenu } from './menu.js';
import { fpGroups, chainProgress, stepDone } from './fp-groups.js';

/**
 * Возвращает обычный вид «Вместе»
 *
 * Вид от первого лица и насмешка - это СЦЕНЫ, собранные под конкретный
 * предмет. У нового предмета такой сцены ещё нет, и оставленный выбор
 * показывал бы пустой кадр с активной кнопкой: человек уже сменил предмет, а
 * приложение всё ещё «в насмешке».
 */
export function resetView() {
  document.querySelectorAll('.modes .underlined').forEach(
    (b) => b.classList.toggle('is-active', b.dataset.view === 'both'));
  work.dataset.view = 'both';
  // Сцену прошлого предмета Python погасил сам (select_item -> viewmodel.stop и
  // taunt.stop), поэтому здесь только отметка: звать выход неоткуда и незачем
  markScene('item');
  document.getElementById('fpbar').hidden = true;
  document.getElementById('tauntbar').hidden = true;
  document.getElementById('wearbar').hidden = true;
  // Камера возвращается к свободной орбите: риг остался от вида от первого лица
  withViewer((w) => w.setViewRig(null));
}

//: Проигрываемая сейчас анимация вида от первого лица
export let fpAction = 'IDLE';

/**
 * Ряд анимаций вида от первого лица
 *
 * Показывается только в этом виде: в обычном ракурсе выбирать нечего, а
 * пустой ряд занимал бы место под моделью.
 */
/**
 * Смена анимации на УЖЕ показанной сцене: приехали одни дорожки
 *
 * Меш, скелет и текстуры у одного оружия те же, поэтому Python и не собирает
 * их заново. Не легли (сцены в кадре почему-то нет) - просим полную сборку,
 * иначе кадр остался бы с прошлой анимацией и без объяснений.
 */
export function applyFpClip(clip) {
  withViewer((w) => {
    if (clip && w.setViewmodelClip && w.setViewmodelClip(clip)) {
      fpClipArrived();
      say('');
      return;
    }
    api.loadFirstPerson(fpAction, true);
  });
}

/** Клип шага в кадре (дорожки или вся сцена): с этого кадра доля и круги -
 *  его. По прыжку доли судить нельзя: переход с другой анимации, с 0.8 на 0,
 *  выглядел как конец шага, и осмотр начинался с середины */
export function fpClipArrived() {
  fpWaiting = 0;
}

/**
 * Пересобирает сцену в руках, если она сейчас в кадре
 *
 * Своя модель заменяет геометрию и на руках тоже - сцена под прошлую
 * геометрию устарела. Полная сборка (`full`): Python сцену уже забыл, но
 * страница просит явно, чтобы не зависеть от порядка.
 */
export async function reloadSceneIfFp() {
  const scene = work.dataset.scene;
  if (scene === 'wear') {
    // «На персонаже» тоже собрана из модели предмета - своя модель меняет её
    sayBusy('Сборка сцены…');
    const res = await api.loadWear(tauntClass, wearSlot);
    if (res.error) sayError(res.error);
    return true;
  }
  if (scene !== 'fp') return false;
  sayBusy('Сборка вида от первого лица…');   // отложенно: подпись о модели успеет прочитаться
  const res = await api.loadFirstPerson(fpAction, true);
  if (res.error) sayError(res.error);
  return true;
}

//: Что играет сейчас: действия по порядку и номер текущего. Группа из
//: нескольких (перезарядка, осмотр) - цепочка, одно действие - повтор его
let fpChain = ['IDLE'];
let fpStep = 0;
//: Клип запрошен и ещё не приехал: с какого времени (0 - не ждём). Пока ждём,
//: в кадре играет прошлый клип, и конец шага по нему не считается
let fpWaiting = 0;

/** Играет цепочку `chain` с начала. `busy` - подпись, пока сцена собирается */
async function playChain(chain, busy = true) {
  fpChain = chain;
  fpStep = 0;
  fpWaiting = performance.now();
  fpAction = chain[0];
  // Из кэша сцена приезжает дорожками за треть секунды - при такой
  // скорости подпись только мигнёт, поэтому она отложенная
  if (busy) sayBusy(`Сборка сцены: ${fpAction}…`);
  const res = await api.loadFirstPerson(fpAction);
  if (res.error) sayError(res.error);
}

/** Следующий шаг цепочки: клип останавливается на последнем кадре, пока не
 *  приедут дорожки следующего, - иначе между шагами мелькал бы повтор */
async function nextStep() {
  fpWaiting = performance.now();
  viewer()?.setViewmodelPlaying?.(false);
  fpStep = (fpStep + 1) % fpChain.length;
  fpAction = fpChain[fpStep];
  const res = await api.loadFirstPerson(fpAction);
  if (res.error) {
    sayError(res.error);
    fpWaiting = 0;
    viewer()?.setViewmodelPlaying?.(true);
  }
}

/**
 * Полоса анимаций в кадре: группы (fp-groups.js) и «Все анимации» со
 * списком сырых действий, включая то, что в группы не вошло
 */
export function showFpActions(actions) {
  const bar = document.getElementById('fpbar');
  bar.innerHTML = '';
  const list = actions || [];
  bar.hidden = list.length < 2 || work.dataset.scene !== 'fp';
  if (bar.hidden) return;

  const { groups } = fpGroups(list);
  for (const g of groups) {
    const b = document.createElement('button');
    b.className = 'tag';
    b.dataset.chain = g.chain.join(' ');
    b.textContent = g.label;
    b.title = g.chain.length > 1
      ? t('Играется цепочкой: {}').replace('{}', g.chain.join(' → ')) : g.chain[0];
    b.addEventListener('click', () => {
      markFp(bar, b);
      playChain(g.chain);
    });
    bar.appendChild(b);
  }
  const more = document.createElement('button');
  more.className = 'tag fp__more';
  more.textContent = 'Все анимации';
  more.addEventListener('click', async (e) => {
    const chosen = await contextMenu(e, list.map((a) => ({ label: a, value: a })));
    if (!chosen) return;
    markFp(bar, more);
    playChain([chosen]);
  });
  bar.appendChild(more);
  // Выбор переживает смену оружия, если у нового он есть; иначе - «Покой»
  const now = fpChain.join(' ');
  const same = bar.querySelector(`.tag[data-chain="${now}"]`)
    || (list.includes(fpAction) && fpChain.length === 1 ? more : null);
  if (!same) { fpChain = [list.includes('IDLE') ? 'IDLE' : list[0]]; fpStep = 0; }
  markFp(bar, same || bar.querySelector('.tag[data-chain]') || more);
  trackFp(bar);
}

function markFp(bar, active) {
  bar.querySelectorAll('.tag').forEach((x) => {
    x.classList.toggle('is-active', x === active);
    x.style.removeProperty('--fp-p');
  });
}

//: Кадр слежения за анимацией от первого лица (requestAnimationFrame)
let fpTrack = 0;

/**
 * Каждый кадр, пока полоса на экране: переход по цепочке и полоса прогресса
 * на выбранной кнопке (--fp-p, вся цепочка целиком). Вьювер отдаёт долю
 * клипа сам (viewmodelProgress). Следит и при выключенных анимациях
 * интерфейса: без этого цепочка не шла бы дальше первого шага
 */
function trackFp(bar) {
  cancelAnimationFrame(fpTrack);
  const step = () => {
    if (bar.hidden) return;
    const w = viewer();
    const p = w?.viewmodelProgress?.();
    if (fpWaiting) {
      // Клип так и не приехал (ошибку сцены покажет её событие) - не стоим
      // на паузе вечно
      if (performance.now() - fpWaiting > 4000) {
        fpWaiting = 0;
        viewer()?.setViewmodelPlaying?.(true);
      }
    } else if (fpChain.length > 1 && stepDone(p, w?.viewmodelLoops?.())) {
      nextStep();
    }
    if (!still()) {
      bar.querySelector('.tag.is-active')?.style.setProperty(
        // Пока ждём клип шага, номер шага уже новый: доля внутри него - ноль,
        // иначе полоса забегала на целый шаг вперёд и откатывалась
        '--fp-p', chainProgress(fpStep, fpChain.length, fpWaiting ? 0 : p));
    }
    fpTrack = requestAnimationFrame(step);
  };
  fpTrack = requestAnimationFrame(step);
}

//: Класс, чью насмешку показываем. Пусто - первый, кто её умеет
export let tauntClass = '';

/**
 * Ряд классов насмешки
 *
 * Одну и ту же насмешку играют до девяти классов, и у каждого своя модель
 * реквизита - выбор меняет и персонажа, и то, что у него в руках.
 */
export function showTauntClasses(classes) {
  const bar = document.getElementById('tauntbar');
  tauntClasses = classes || [];
  // Выбор общий у двух сцен: насмешки и шапки на персонаже. Какую пересобрать,
  // решает сцена, открытая в момент выбора
  const scene = work.dataset.scene;
  bar.hidden = tauntClasses.length < 2 || (scene !== 'taunt' && scene !== 'wear');
  if (bar.hidden) return;
  if (!tauntClasses.includes(tauntClass)) tauntClass = tauntClasses[0];
  markClass();
}

//: Классы, из которых выбирает кнопка класса
let tauntClasses = [];
const classBtn = document.getElementById('classpick');
const markClass = () => { classBtn.textContent = `${tauntClass} ▾`; };

classBtn.addEventListener('click', async () => {
  const r = classBtn.getBoundingClientRect();
  // Кнопка у нижнего края кадра: меню встаёт над ней (menu.js сдвинет его в
  // окно, если сверху не хватит места)
  const at = { preventDefault() {}, clientX: r.left, clientY: r.top - 12 - tauntClasses.length * 36 };
  const name = await contextMenu(at, tauntClasses.map((c) => ({ label: c, value: c })));
  if (!name || name === tauntClass) return;
  tauntClass = name;
  markClass();
  sayBusy(`Сборка сцены: ${name}…`);
  const scene = work.dataset.scene;
  // У другого класса другое оружие: слот выбираем заново, первый
  if (scene === 'wear') wearSlot = '';
  const res = scene === 'wear' ? await api.loadWear(name, '') : await api.loadTaunt(name);
  if (res.error) sayError(res.error);
});

//: Какое оружие у персонажа в сцене «На персонаже». Пусто - первый слот класса
export let wearSlot = '';

//: Подписи слотов раскладки. У шпиона второй слот - сапёр, четвёртый -
//: набор маскировки, у инженера четвёртый - КПК постройки
const SLOT_TITLES = {
  primary: 'Основное', secondary: 'Вспомогательное', building: 'Сапёр',
  melee: 'Ближний бой', pda: 'КПК',
};

/**
 * Ряд слотов оружия в сцене «На персонаже»
 *
 * Слоты приходят от воркера: у каждого класса свой набор (у инженера и
 * шпиона - четыре, у остальных три). Стойку персонажа задаёт слот, поэтому
 * выбор пересобирает сцену целиком.
 */
export function showWearSlots(ev) {
  const bar = document.getElementById('wearbar');
  bar.querySelectorAll('.tag').forEach((b) => b.remove());
  const slots = ev.slots || [];
  // Класс сцены - и при одном слоте: подпись кнопки класса не должна отстать
  if (ev.tf2_class) { tauntClass = ev.tf2_class; markClass(); }
  // Один слот - выбирать нечего: оружие в руках стоит в своём слоте
  bar.hidden = slots.length < 2 || work.dataset.scene !== 'wear';
  if (bar.hidden) return;
  wearSlot = ev.slot || slots[0];
  for (const slot of slots) {
    const b = document.createElement('button');
    b.className = 'tag' + (slot === wearSlot ? ' is-active' : '');
    b.textContent = t(SLOT_TITLES[slot] || slot);
    b.addEventListener('click', async () => {
      if (slot === wearSlot) return;
      wearSlot = slot;
      bar.querySelectorAll('.tag').forEach(
        (x) => x.classList.toggle('is-active', x === b));
      sayBusy('Сборка сцены…');
      const res = await api.loadWear(tauntClass, slot);
      if (res.error) sayError(res.error);
    });
    bar.appendChild(b);
  }
}

//: Какая спец-сцена сейчас в кадре: '' | 'none' | 'crit' | 'death'.
//: От неё зависит, КУДА кладётся текстура - на билборд или на персонажа
export let sceneKind = '';
//: Текстура персонажа в сцене (у эффекта смерти - игровая по умолчанию)
export let sceneModelTex = '';
//: Что человек положил сам. Сцена приходит позже текстуры и наоборот -
//: помним последнее, иначе сборка сцены стирала уже выбранную картинку
let userTextures = {};
//: Игровой огонь: лист кадров и как его показывать (режим горения)
let sceneFire = null;
//: Какой слой огня сейчас во вьювере: applyView зовут после каждого действия,
//: а перезапускать ради этого анимацию незачем
let fireKey = '';

/** Спец-сцена прошлого предмета: у обычной модели её нет */
export function forgetSpecialScene() { sceneKind = ''; fireKey = ''; }

/**
 * Слой огня поверх раскраски солдата
 *
 * Своя картинка - один кадр, игровая - лист из 121. Повтор плитки и скорость
 * одни и те же: их задаёт материал игры, а не текстура.
 */
function showFire(force = false) {
  const own = Object.values(userTextures || {})[0];
  const base = sceneFire || {};
  const spec = own
    ? { frames: [api.fileUrl(own)], fps: 0, scale: base.scale || 1 }
    : (base.atlas ? { ...base, atlas: api.fileUrl(base.atlas) } : null);
  const key = JSON.stringify(spec);
  if (!force && key === fireKey) return;
  fireKey = key;
  withViewer((w) => w.setFireOverlay && w.setFireOverlay(spec));
}

/**
 * Сцена спец-режима
 *
 * Крит - персонаж и билборд над ним. Лёд и золото - тот же персонаж, но
 * текстура ложится на него целиком. Огонь горит поверх его раскраски.
 */
export function showSpecialScene(ev) {
  sceneKind = ev.scene_kind || 'none';
  sceneModelTex = ev.model_texture || '';
  sceneFire = ev.fire || null;
  userTextures = {};
  // Огонь прошлого режима: у льда и крита его нет
  fireKey = '';
  if (sceneKind !== 'fire') withViewer((w) => w.setFireOverlay && w.setFireOverlay(null));
  // Кнопки стилей прошлого предмета к спец-режиму не относятся: своего
  // события skins тут не будет, и они остались бы в ряду навсегда
  document.querySelectorAll('#skinbar .tag').forEach((b) => b.remove());

  if (sceneKind === 'none') {
    withViewer((w) => w.resetViewer && w.resetViewer());
    sayInfo('Положите картинку в кадр - модели у этого режима нет');
    return;
  }

  // Настоящую сцену - солдата с анимацией смерти - собирает воркер, и это
  // секунды на распаковку модели. Кубики в это время показывать нельзя: при
  // каждом переключении режима в кадре мелькал бы человечек из коробок
  if (ev.pending) {
    say('Собираем сцену…');
    return;
  }
  specialFallback();
}

//: Кубики вместо персонажа. Запасной кадр: сюда приходят, если сцену собрать
//: не вышло - игры нет или модель не разобралась
function specialFallback() {
  const modelUrl = sceneModelTex ? api.fileUrl(sceneModelTex) : '';
  withViewer((w) => w.loadCritHitScene('', modelUrl));
  say(sceneKind === 'crit'
    ? 'Картинка ляжет билбордом над персонажем'
    : 'Картинка ляжет на персонажа - так эффект выглядит в игре');
}

/** Сцену собрать не вышло: показываем то, что показывали раньше */
export function specialSceneFailed(error) {
  if (!sceneKind || sceneKind === 'none') return false;
  specialFallback();
  if (error) sayError(error);       // причина важнее подсказки про картинку
  return true;
}

/**
 * Настоящая сцена спец-режима: солдат играет ту смерть, что подходит режиму
 *
 * Крит - выстрел в голову и билборд над телом, лёд и золото - удар в спину;
 * огонь - своя анимация горения. Сцена та же, что у насмешки, поэтому и
 * показывает её общий загрузчик.
 */
export function showSpecialAnimated(ev) {
  const url = specialTextureUrl();
  withViewer((w) => {
    w.setViewRig(null);
    w.loadViewmodelAnimated(ev.scene, 0);
    if (sceneKind === 'crit') w.setCritSprite(url);
    // Лёд и золото: игра ЗАМЕНЯЕТ материалы трупа целиком, одна картинка
    // ложится на всё тело, а не по материалам. Огонь - слой поверх них
    else if (sceneKind !== 'fire' && url) w.updateTextureFromDataUrl(url);
  });
  // Материалы сцены новые: слой огня надо повесить заново
  if (sceneKind === 'fire') showFire(true);
  // Сообщение о сборке иначе висит поверх кадра до конца сеанса: своего
  // события «готово» у прогресса нет
  say('');
  // Текстуры персонажа приехали раньше сцены - разложить их некуда было
  if (sceneKind === 'crit' || sceneKind === 'fire') refreshView();
}

//: Что сейчас показывать в спец-сцене: своя картинка человека, иначе игровая
function specialTextureUrl() {
  const own = Object.values(userTextures || {})[0];
  if (own) return api.fileUrl(own);
  return sceneModelTex ? api.fileUrl(sceneModelTex) : '';
}

/**
 * Текстура спец-сцены: у крита - билборд, у эффекта смерти - сам персонаж
 *
 * Что сцена забрала на себя: 'all' - всё, обычная раздача по материалам не
 * нужна; 'card' - только картинку карточки, меши красятся своими текстурами;
 * '' - ничего.
 */
export function applySpecialTexture(textures) {
  if (!sceneKind || sceneKind === 'none') return '';
  userTextures = textures || {};
  const url = specialTextureUrl();
  if (sceneKind === 'crit') {
    // Крит забирает на себя ТОЛЬКО билборд: сам солдат красится своими
    // игровыми текстурами, и обычную раздачу по материалам перебивать нельзя
    // - иначе он остаётся серым
    withViewer((w) => w.updateCritHitTexture(url));
    return 'card';
  }
  if (sceneKind === 'fire') {
    // Огонь в игре не заменяет раскраску, а горит поверх неё
    showFire();
    return 'card';
  }
  // На кубиках-заглушке это тоже работает: текстура кладётся на все меши
  // сцены, чем бы она ни была
  withViewer((w) => w.updateTextureFromDataUrl(url));
  return 'all';
}

/** Небо: шесть граней кубмапой вместо модели */
//: Какие картинки сейчас на небе мода: applyView зовут после каждого
//: действия, а грузить шесть граней заново ради этого незачем
let modSkyKey = '';

/**
 * Мод неба из VPK: кубмапа из картинок его карточек
 *
 * Грани - это карточки альбома мода (`mod_sky` - какая на какой). Картинка
 * берётся та, что сейчас на карточке: своя, если её заменили, иначе мода -
 * поэтому замена видна на небе сразу
 */
export function showModSky(st) {
  const sky = st.mod_sky || {};
  const faces = Object.fromEntries(Object.entries(sky)
    .map(([face, card]) => [face, (st.textures || {})[card]])
    .filter(([, path]) => path));
  const key = JSON.stringify(faces);
  if (!Object.keys(faces).length || work.dataset.scene !== 'item') {
    modSkyKey = '';
    return;
  }
  if (key === modSkyKey) return;
  modSkyKey = key;
  withViewer((w) => w.loadSkybox(
    Object.fromEntries(Object.entries(faces).map(([f, p]) => [f, api.fileUrl(p)]))));
}

export function showSkybox(ev) {
  const faces = (ev && ev.faces) || {};
  const names = Object.keys(faces);
  if (!names.length) {
    sayInfo('У этого неба граней в игре не нашлось');
    return;
  }
  withViewer((w) => w.loadSkybox(
    Object.fromEntries(names.map((f) => [f, api.fileUrl(faces[f])]))));
  say(names.length < 6 ? `Найдено граней: ${names.length} из 6` : '');

  // Панорама - ПЕРВАЯ карточка ленты. Это единственное место, куда кладут
  // фото 360°: грани принимают по одной картинке каждая, а панорама одна на
  // все шесть - Python режет её сам и присылает результат гранями. Без этой
  // карточки перенос фото 360° не делал ничего вовсе: класть его было некуда
  const pano = (ev && ev.pano_key) || '__pano__';
  cardTitles[pano] = 'Панорама 360°';
  showMaterials([pano, ...names], { ...faces, [pano]: (ev && ev.pano) || '' });
  // Пустая карточка - шахматка без объяснений, и её принимали за отсутствие
  // функции. Подпись говорит, что сюда класть, с картинкой она не нужна
  if (!(ev && ev.pano)) {
    const hint = document.createElement('span');
    hint.className = 'frame__hint';
    hint.textContent = 'Перетащите фото 360° (2:1) - оно разрежется на все шесть граней';
    document.querySelector(`.frame[data-mat="${pano}"] .frame__img`).appendChild(hint);
  }

  // Небо приходит своим событием, минуя applyView, поэтому кнопки прошлого
  // предмета надо убрать здесь: у неба нет ни команд, ни варианта, ни стилей
  document.querySelectorAll('.teams .tag').forEach((b) => { b.hidden = true; });
  document.getElementById('skinbar').hidden = true;
  document.getElementById('stylebar').hidden = true;
}

/** Статичная сцена вида от первого лица */
export async function showFirstPerson(objPath, rig) {
  const w = viewer();
  if (!w) return;
  try {
    const obj = await (await fetch(api.fileUrl(objPath))).text();
    // Риг до загрузки: сцена уже стоит там, где надо относительно глаза, и
    // центрировать её нельзя - двигается камера
    w.setViewRig(rig);
    w.loadModelFromContent(obj, '', 0, 0, 0, 1, 0);
    say('');
  } catch (err) {
    sayError(`Не удалось показать сцену: ${err.message}`);
  }
}

// Сцена: сам предмет, руки или насмешка
//
// Вид от первого лица и насмешка - не ракурсы, а собранные сцены: их ставит
// отдельный воркер, и снять их обязан тот же, кто поставил. «Сам по себе» -
// это и есть выход, названный словом, а не побочное действие чего-то другого
async function showScene(name) {
  if ((work.dataset.scene || 'item') === name) return;   // уже показано
  markScene(name);
  // Резка модели относится к обычной геометрии: на сцене её карта частей уже
  // не про то, что в кадре. Откладываем, а не закрываем насовсем - по выходу
  // режим вернётся сам (см. resumeParts)
  if (name !== 'item') suspendParts();

  if (name === 'wear') {
    say('Сборка сцены…');
    withViewer((w) => w.setViewRig(null));   // камера свободная, как у насмешки
    const res = await api.loadWear(tauntClass, wearSlot);
    if (res.error) sayError(res.error);
    return;
  }
  if (name === 'taunt') {
    say('Сборка насмешки…');
    withViewer((w) => w.setViewRig(null));   // у насмешки камера свободная
    const res = await api.loadTaunt(tauntClass);
    if (res.error) sayError(res.error);
    return;
  }
  if (name === 'fp') {
    say('Сборка вида от первого лица…');
    await flushFitSave();       // сцена собирается из SMD - с последней подгонкой
    const res = await api.loadFirstPerson(fpAction);
    if (res.error) sayError(res.error);
    return;   // риг придёт вместе со сценой: порядок ответа и события не задан
  }

  // Свободная камера - это ещё не выход: сцену собирал отдельный воркер, и без
  // возврата обычной модели оружие так и осталось бы в руках. Кадр обычного
  // превью уже есть, поэтому Python
  // пересобирать нечего - он лишь снимает сцену и подложку. Выход у обеих
  // сцен один: `leave_first_person` гасит и вьюмодель, и насмешку - обе держат
  // подложку с текстурами персонажа (см. session.leave_first_person)
  withViewer((w) => w.setViewRig(null));
  document.getElementById('fpbar').hidden = true;
  document.getElementById('tauntbar').hidden = true;
  document.getElementById('wearbar').hidden = true;
  if (root.dataset.section === 'particles') return;   // там вьювера моделей нет
  applyView(await api.leaveFirstPerson());
  if (lastModel) await showModel(lastModel);
  // Строго после модели: `showModel` заново связывает части со вьювером
  // (bindParts закрывает режим), и включённый до него он тут же и погас бы
  await resumeParts();
}

/**
 * Отмечает выбранную сцену
 *
 * Состояние живёт на `.work`: по нему открываются ряды выбора анимации и
 * класса, и спрашивать его у кнопок значило бы держать одно и то же в
 * разметке дважды
 *
 * Кнопки ищем ТОЛЬКО в своём ряду: `data-scene` есть и у точек эффекта («в
 * мире» / «на модели») - там это сцена самой точки, и общий поиск красил бы
 * заодно их.
 */
function markScene(name) {
  work.dataset.scene = name;
  document.querySelectorAll('.half__bar--scenes [data-scene]').forEach(
    (b) => b.classList.toggle('is-active', b.dataset.scene === name));
}

document.querySelector('.half__bar--scenes').addEventListener('click', (e) => {
  const btn = e.target.closest('[data-scene]');
  if (btn) showScene(btn.dataset.scene);
});
