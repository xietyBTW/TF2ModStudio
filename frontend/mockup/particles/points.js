/*
 * Контрольные точки эффекта
 *
 * Движок держит их у себя (позиция, углы, пресет движения), отсюда только
 * команды. Номера точек, которые эффекту нужны, считает Python - вычитать их
 * из дерева свойств вручную никто не станет.
 */

import * as api from '../api.js';
import { pickCpModel } from './cpmodel.js';
import { t } from '../i18n.js';
import { say, sayError, withParticles } from '../stage.js';
import { pSystem } from './state.js';

// Контрольные точки
// Движок держит их у себя (позиция, углы, пресет движения), отсюда только
// команды. Номера точек, которые эффекту нужны, считает Python - вычитать их
// из дерева свойств вручную никто не станет

export const cpBox = document.getElementById('cp');
const cpEl = (id) => document.getElementById(id);
//: Текущая точка. Ноль - та, вокруг которой строится почти всё в TF2
let cpIndex = 0;
//: Точки крепления выбранной модели (имя, позиция, углы)
let cpAttachments = [];
//: Куда игра вешает точку 0 открытого эффекта: {attachment, rootbone} из
//: items_game, null - эффект не необычный
let cpRule = null;

const cpNum = (id) => Number(cpEl(id).value) || 0;

//: Своё состояние у каждой точки. Без него правка после переключения
//: переносила бы на новую точку значения предыдущей
const cpState = new Map();
const CP_FIELDS = ['cp-x', 'cp-y', 'cp-z', 'cp-p', 'cp-yaw', 'cp-r',
                   'cp-amp', 'cp-period'];
//: Точка, которую ещё не трогали: в начале сцены, без углов и движения
const CP_DEFAULT = { values: [0, 0, 0, 0, 0, 0, 24, 2], motion: 'none' };
//: Положения точек «в мире» и «на модели» порознь. Сцена «в мире» раньше
//: только прятала модель, а точки оставались на её точках крепления, и
//: эффект висел и крутился так, будто модель всё ещё под ним
const cpSaved = { world: new Map(), model: new Map() };
//: Какая сцена сейчас: точки переносятся только при настоящей смене
let cpOnModel = false;

/** Показывает в полях состояние выбранной точки */
function cpLoad() {
  const st = cpState.get(cpIndex) || CP_DEFAULT;
  CP_FIELDS.forEach((id, n) => { cpEl(id).value = st.values[n]; });
  cpEl('cp-motion').value = st.motion;
  cpMotionOpts();
  // Точка крепления - тоже часть состояния точки: у оружия точка 0 висит на
  // unusual_0, точка 1 - на unusual_1, и список должен показывать своё
  cpEl('cp-attach').value = st.attach ?? '';
}

/** Шлёт движку положение, углы и пресет движения текущей точки */
function cpPush() {
  // Точка, сдвинутая руками, уже не на attachment
  cpEl('cp-attach').value = '';
  cpPushIndex(cpIndex, { values: CP_FIELDS.map(cpNum),
                         motion: cpEl('cp-motion').value });
}

/** Запоминает состояние точки и отдаёт его движку */
function cpPushIndex(index, st) {
  const [x, y, z, p, yaw, r, amp, period] = st.values;
  cpState.set(index, st);
  withParticles((w) => {
    w.setControlPoint(index, x, y, z);
    // Нулевые углы - это тоже углы: сбрасывать ориентацию надо явно, иначе
    // точка осталась бы повёрнутой от прошлой правки
    if (p || yaw || r) w.setControlPointOrientation(index, p, yaw, r);
    else w.clearControlPointOrientation(index);
    w.setControlPointMotion(index, st.motion, amp, period);
  });
}

//: Зачем эффекту точка - по модулю, который её читает (роль считает
//: Python). Роли без подписи нет: номер честнее выдуманного смысла
const ROLE_TEXT = {
  origin: 'откуда растёт', path_end: 'куда летит', follow: 'за чем движется',
  pull: 'к чему тянется', distance: 'от чего расстояние', remap: 'значение из кода',
};
//: Номера сверх нужных эффекту, которые открывает «+ ещё»: точек 64, но
//: руками ставят первые несколько
const SPARE_POINTS = 8;
//: Показаны ли точки, которые эффекту не нужны
let cpShowAll = false;

/** Вкладки точек: нужные эффекту - с подписью, остальные - по «+ ещё» */
export async function cpFillIndexes() {
  const box = cpEl('cp-index');
  const res = pSystem ? await api.particleControlPoints(pSystem) : { used: [], roles: {} };
  cpFollowRule(res.game_attach || null);
  const used = res.used || [];
  const roles = res.roles || {};
  const spare = cpShowAll ? Array.from({ length: SPARE_POINTS }, (_, i) => i) : [];
  // Текущая видна всегда, даже если эффекту она не нужна
  const shown = [...new Set([...(used.length ? used : [0]), ...spare, cpIndex])]
    .sort((a, b) => a - b);

  box.replaceChildren(...shown.map((i) => {
    const b = document.createElement('button');
    b.type = 'button';
    b.className = 'cp__tab' + (i === cpIndex ? ' is-active' : '')
      + (used.includes(i) ? '' : ' is-spare');
    b.setAttribute('role', 'tab');
    b.setAttribute('aria-selected', String(i === cpIndex));
    const name = document.createElement('span');
    name.textContent = `Точка ${i}`;
    b.append(name);
    const role = ROLE_TEXT[roles[i]];
    if (role) {
      const sub = document.createElement('small');
      sub.textContent = role;
      b.append(sub);
    }
    if (!used.includes(i)) b.title = t('Этой точкой эффект не пользуется');
    b.addEventListener('click', () => {
      cpIndex = i;
      cpLoad();            // у каждой точки своё положение
      cpFillIndexes();
    });
    return b;
  }));

  const more = document.createElement('button');
  more.type = 'button';
  more.className = 'textbtn textbtn--sm cp__all';
  more.textContent = cpShowAll ? 'Только нужные' : '+ ещё';
  more.title = t(cpShowAll ? 'Спрятать точки, которыми эффект не пользуется'
                           : 'Точки, которыми эффект не пользуется');
  more.addEventListener('click', () => { cpShowAll = !cpShowAll; cpFillIndexes(); });
  box.append(more);
}

/** Другой эффект - другое правило крепления: точка 0, стоявшая по прошлому
 *  правилу, переезжает. Выбранную руками не трогаем */
function cpFollowRule(rule) {
  const before = cpZeroAt();
  cpRule = rule;
  const st = cpState.get(0);
  if (!cpOnModel || st?.attach !== String(before)) return;
  const after = cpZeroAt();
  if (after < 0 || after === before) return;
  cpPlace(0, after);
  if (cpIndex === 0) cpLoad();
}

/** Размах и период нужны, только когда точка движется */
function cpMotionOpts() {
  cpEl('cp-motion-opts').hidden = cpEl('cp-motion').value === 'none';
}

for (const id of ['cp-x', 'cp-y', 'cp-z', 'cp-p', 'cp-yaw', 'cp-r',
                  'cp-amp', 'cp-period']) {
  cpEl(id).addEventListener('input', cpPush);
}
cpEl('cp-motion').addEventListener('change', () => { cpMotionOpts(); cpPush(); });

cpEl('cp-reset').addEventListener('click', () => {
  cpState.delete(cpIndex);
  cpLoad();
  cpPush();
});

// Гизмо двигает весь эффект или только открытую систему: обычно эффект
// сдвигают целиком, а родитель без детей разваливает его на части
document.getElementById('cp-scope').addEventListener('click', (e) => {
  const btn = e.target.closest('[data-scope]');
  if (!btn) return;
  for (const b of btn.parentElement.children) b.classList.toggle('is-active', b === btn);
  withParticles((w) => w.setGizmoScope(btn.dataset.scope));
});

document.getElementById('pcpbtn').addEventListener('click', (e) => {
  cpBox.hidden = !cpBox.hidden;
  e.currentTarget.classList.toggle('is-active', !cpBox.hidden);
  e.currentTarget.setAttribute('aria-pressed', String(!cpBox.hidden));
  // Ручка в кадре нужна только пока точку правят
  withParticles((w) => w.setGizmoVisible(!cpBox.hidden));
  if (!cpBox.hidden) cpFillIndexes();
});

//: Подпись модели, которую сейчас разбирает Crowbar: сцена придёт событием
let cpPendingLabel = '';

cpEl('cp-model').addEventListener('click', async () => {
  const pick = await pickCpModel();
  if (!pick) return;
  if (pick.mode === 'cache') {
    // Уже разобрано: меш собирается сразу, без Crowbar
    say('Сборка меша модели…');
    const scene = await api.particleModelScene(pick.qc);
    if (scene.error) { sayError(scene.error); return; }
    applyCpModelScene(scene, pick.label);
    return;
  }
  cpPendingLabel = pick.label;
  say('Разбор модели…');
  const res = await api.particleModelLoad(pick.mode, pick.key);
  if (res.error) { sayError(res.error); cpPendingLabel = ''; }
});

/** Сцена модели приехала (событие cp_model или ответ по кэшу) */
export function showCpModel(ev) {
  if (ev.error) { sayError(ev.error); cpPendingLabel = ''; return; }
  applyCpModelScene(ev.scene, cpPendingLabel);
  cpPendingLabel = '';
}

function applyCpModelScene(scene, label) {
  // Корневая кость - первой: к ней игра цепляет анюжуал косметики
  // (attach_to_rootbone), и у шапки это голова, а не ноги
  const root = scene.root
    ? [{ ...scene.root, name: scene.root.name + ' (' + t('корень') + ')', root: true }] : [];
  cpAttachments = [...root, ...(scene.attachments || [])];
  cpEl('cp-model-name').textContent = label || '';
  // Номера точек крепления прошлой модели больше ничего не значат
  for (const st of cpState.values()) delete st.attach;
  cpSaved.model.clear();

  const sel = cpEl('cp-attach');
  sel.innerHTML = '';
  sel.append(new Option('- не выбрана -', ''));
  cpAttachments.forEach((a, i) => sel.append(new Option(a.name, String(i))));
  sel.disabled = cpAttachments.length === 0;

  withParticles((w) => {
    w.loadModelObj(scene.obj, scene.textures || {});
    w.setModelVisible(true);
  });
  cpScene(true);
  // Точки сразу туда, куда вешает игра: точка 0 - см. cpZeroAt, точки 1..5 -
  // на «unusual_1».. «unusual_5» (control_point_N в items_game). Иначе эффект
  // шапки стоял в нуле сцены, а сама шапка - на высоте головы
  const byName = new Map(cpAttachments.map((a, i) => [a.name.toLowerCase(), i]));
  const zero = cpZeroAt();
  if (zero >= 0) {
    cpPlace(0, zero);
    for (let n = 1; n <= 5; n++) {
      const i = byName.get('unusual_' + n);
      if (i !== undefined) cpPlace(n, i);
    }
    cpLoad();
  }
  say('');
}

/**
 * Номер точки крепления для точки 0 или -1 (econ_entity.cpp,
 * UpdateSingleParticleSystem): attachment эффекта из items_game, если он есть
 * у модели, иначе корневая кость при attach_to_rootbone. У 30 старых
 * эффектов (Burning Flames, Green Energy) attachment нет или он
 * «muzzle», которого у шапок нет, - на шапке с полным скелетом они висят на
 * тазу, а не на «unusual». Не необычный эффект - как большинство: «unusual»
 * или «unusual_0», иначе корень
 */
function cpZeroAt() {
  const byName = new Map(cpAttachments.map((a, i) => [a.name.toLowerCase(), i]));
  const root = cpAttachments[0]?.root ? 0 : -1;
  if (!cpRule) return byName.get('unusual') ?? byName.get('unusual_0') ?? root;
  const at = cpRule.attachment ? byName.get(cpRule.attachment.toLowerCase()) : undefined;
  return at ?? (cpRule.rootbone ? root : -1);
}

/** Ставит точку ровно на attachment номер `at`: в игре эффект висит именно там */
function cpPlace(index, at) {
  const a = cpAttachments[at];
  const st = cpState.get(index) || CP_DEFAULT;
  // Положение «в мире» запоминаем до крепления - к нему вернёт «В мире»
  if (st.attach === undefined && !cpSaved.world.has(index)) cpSaved.world.set(index, st);
  const r1 = (v) => Math.round(v * 10) / 10;
  cpPushIndex(index, { values: [...a.pos.map(r1), ...a.angles.map(r1),
                                st.values[6], st.values[7]],
                       motion: st.motion, attach: String(at) });
}

cpEl('cp-attach').addEventListener('change', () => {
  const at = Number(cpEl('cp-attach').value);
  if (!cpAttachments[at]) return;
  cpPlace(cpIndex, at);
  cpLoad();
});

/** Переключает сцену: пустое пространство или модель под эффектом */
function cpScene(onModel) {
  const changed = onModel !== cpOnModel;
  if (changed) cpSwapPoints(onModel);
  cpOnModel = onModel;
  document.querySelectorAll('#cp-scene .tag').forEach(
    (b) => b.classList.toggle('is-active', (b.dataset.scene === 'model') === onModel));
  // Модель и точка крепления - только «на модели»: в мире они ничего не меняют
  cpEl('cp-model-opts').hidden = !onModel;
  withParticles((w) => {
    w.setModelVisible(onModel);
    // Заново: уже родившиеся частицы иначе досматривали жизнь по старой
    // сцене, и смена выглядела так, будто ничего не произошло
    if (changed) w.restartEffect();
  });
}

/**
 * Точки при смене сцены: «в мире» - туда, где стояли до крепления (иначе в
 * начало), «на модели» - обратно на точки крепления. Правки, сделанные в
 * одной сцене, другой не задевают
 */
function cpSwapPoints(onModel) {
  if (onModel) {
    for (const [index, st] of cpSaved.model) {
      // Последняя правка «в мире» - её и вернёт следующий уход в мир
      cpSaved.world.set(index, cpState.get(index) || CP_DEFAULT);
      cpPushIndex(index, st);
    }
    cpSaved.model.clear();
  } else {
    for (const [index, st] of cpState) {
      if (st.attach === undefined) continue;
      cpSaved.model.set(index, st);
      cpPushIndex(index, cpSaved.world.get(index) || CP_DEFAULT);
    }
  }
  cpLoad();
}

document.getElementById('cp-scene').addEventListener('click', (e) => {
  const b = e.target.closest('[data-scene]');
  if (b) cpScene(b.dataset.scene === 'model');
});
