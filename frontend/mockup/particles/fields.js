/*
 * Поля редактора: ползунок, число, цвет, атрибут экспертного режима
 *
 * Крутилки описаны в Python (services/simple_params) - здесь только поля и
 * отправка значений. Список параметров, границы и подписи приходят готовыми:
 * схема одна на панель приложения и на эту страницу.
 */

import * as api from '../api.js';
import { curveFraction, curveValue } from '../curve.js';
import { say, sayError, particles, withParticles } from '../stage.js';
import { pSystem, pcfNodes, setDiff } from './state.js';
import { showParams } from './params.js';
import { fillTree, setTitle } from './tree.js';
import { ensureEffectMaterials } from './materials.js';
import { paintTrack } from '../util.js';

/**
 * Дорожка ползунка. Границы у неё МЯГКИЕ (сколько нужно в 99% эффектов), а
 * поле рядом принимает и жёсткие: в стоке встречаются emission_rate под
 * миллион, и запрет на них молча испортил бы чужой эффект.
 */
export function sliderField(value, param, onLive, onDone) {
  const r = document.createElement('input');
  r.className = 'slider';
  r.type = 'range';
  r.min = 0; r.max = 1000; r.step = 1;
  r.value = Math.round(curveFraction(param, value) * 1000);
  const read = () => {
    const v = curveValue(param, Number(r.value) / 1000);
    return param.decimals ? Number(v.toFixed(param.decimals)) : Math.round(v);
  };
  // Пока тянут - только показываем, в Python уходит отпускание, иначе одно
  // перетаскивание давало бы сотню правок файла
  r.addEventListener('input', () => onLive(read()));
  r.addEventListener('change', () => onDone(read()));
  return r;
}

/** Поле одного числа. Возвращает input; onEdit получает уже число */
export function numberField(value, param, onEdit) {
  const i = document.createElement('input');
  i.className = 'input input--num';
  i.type = 'number';
  i.step = param.decimals ? String(10 ** -param.decimals) : '1';
  i.min = param.hard_min;
  i.max = param.hard_max;
  i.value = Number(value).toFixed(param.decimals);
  // Пока модуля под параметром нет, поле показывает умолчание Source бледным:
  // именно его эффект и получит, если правку не тронуть
  i.classList.toggle('is-placeholder', param.value === null);
  i.addEventListener('change', () => {
    const v = Math.min(param.hard_max, Math.max(param.hard_min, Number(i.value)));
    i.value = v.toFixed(param.decimals);
    onEdit(v);
  });
  return i;
}

/**
 * Дорожка и поле на одно значение: тянуть удобнее, вписать точнее
 *
 * Дорожка ходит по мягким границам, поле принимает и жёсткие - поэтому
 * значение из чужого эффекта (emission_rate под миллион) правится вручную,
 * а дорожка просто упирается в край. `onLive` - значение, пока дорожку тянут
 */
export function valueControl(value, param, onEdit, onLive) {
  const field = numberField(value, param, onEdit);
  const track = sliderField(value, param, (v) => {
    field.value = v.toFixed(param.decimals);
    onLive?.(v);
  }, onEdit);
  // Закраска от нуля: у гравитации и спина ноль посередине дорожки
  const zero = param.min < 0 && param.max > 0 ? curveFraction(param, 0) * 1000 : null;
  paintTrack(track, zero);
  field.addEventListener('input', () => {
    track.value = Math.round(curveFraction(param, Number(field.value)) * 1000);
    paintTrack(track, zero);
  });
  return { fields: [field], track };
}

/**
 * Диапазон: одна дорожка с двумя ручками и залитым отрезком между ними, два
 * поля для точного ввода. Две дорожки подряд не говорили, какая из них «от»,
 * а какая «до». У `ordered` начало не обгоняет конец, у «начало - конец»
 * (рост размера) концы независимы
 */
export function rangeControl(values, param, onEdit, onLive) {
  const vals = values.slice();
  const put = (n, x) => {
    vals[n] = x;
    if (!param.ordered) return;
    if (n === 0) vals[1] = Math.max(vals[1], x);
    else vals[0] = Math.min(vals[0], x);
  };
  const track = document.createElement('div');
  track.className = 'dual';
  const fill = document.createElement('i');
  fill.className = 'dual__fill';
  const fields = vals.map((v, n) => numberField(v, param, (x) => {
    put(n, x);
    show();
    onEdit(vals.slice());
  }));
  const knobs = vals.map((v, n) => sliderField(v, param, (x) => {
    put(n, x);
    show();
    onLive?.(vals.slice());
  }, (x) => {
    put(n, x);
    onEdit(vals.slice());
  }));
  // Ручки и отрезок по значениям; поля - только когда тянут дорожку, иначе
  // набор числа перебивался бы его же округлением
  const place = () => {
    vals.forEach((v, n) => { knobs[n].value = Math.round(curveFraction(param, v) * 1000); });
    const [a, b] = knobs.map((k) => Number(k.value) / 10);
    fill.style.left = Math.min(a, b) + '%';
    fill.style.width = Math.abs(b - a) + '%';
  };
  const show = () => {
    vals.forEach((v, n) => { fields[n].value = Number(v).toFixed(param.decimals); });
    place();
  };
  fields.forEach((f, n) => f.addEventListener('input', () => {
    vals[n] = Number(f.value);
    place();
  }));
  track.append(fill, ...knobs);
  place();
  return { fields, track };
}

/** Цвет как #rrggbb; альфу сохраняем - её правит отдельный параметр */
export function colorField(rgba, onEdit) {
  const i = document.createElement('input');
  i.type = 'color';
  i.className = 'colorfield';
  const hex = (n) => Math.max(0, Math.min(255, n | 0)).toString(16).padStart(2, '0');
  i.value = '#' + hex(rgba[0]) + hex(rgba[1]) + hex(rgba[2]);
  i.addEventListener('change', () => {
    const n = parseInt(i.value.slice(1), 16);
    onEdit([(n >> 16) & 255, (n >> 8) & 255, n & 255, rgba[3] ?? 255]);
  });
  return i;
}

/**
 * Значение крутилки - сразу в превью, без Python: пока тянут ползунок,
 * эффект меняется на глазах и не начинается заново. Работает, когда модуль
 * на месте (`targets` не пуст); false - показать нечем
 */
export function previewParam(param, value) {
  const targets = param.targets || [];
  if (!targets.length) return false;
  const slots = param.kind === 'range' || param.kind === 'color_pair' ? value : [value];
  const edits = targets.map((x) => {
    let v = slots[x.slot];
    if (typeof v === 'number') {
      v *= x.scale;
      if (x.type === 'integer') v = Math.round(v);
    }
    if (x.type === 'bool') v = Boolean(v);
    return { group: x.group, index: x.index, attr: x.attr,
             component: x.component, type: x.type, value: v };
  });
  withParticles((w) => w.previewAttrs && w.previewAttrs(pSystem, edits));
  return true;
}

/** Отправляет правку и переливает результат в живое превью */
export async function editParam(param, value) {
  // Значение уже в кадре - итог из Python сверяется по составу и эффект не
  // перезапускается. Если правка создала модуль, состав другой, и превью
  // соберётся заново само
  const live = previewParam(param, value);
  const res = await api.setParticleParam(pSystem, param.key, value);
  // Файл правку не принял - кадр возвращается к тому, что в файле
  if (res.error && live) previewParam(param, param.value);
  await applyEdit(res, live);
}

/**
 * Быстрая правка всего эффекта: масштаб, плотность, темп. Меняется сразу
 * много систем, поэтому эффект в кадре собирается заново
 */
export async function quickEdit(kind, up) {
  await applyEdit(await api.quickParticleEdit(pSystem, kind, up), false);
}

/** Ответ правки - в превью, метки «изменено» и панель */
async function applyEdit(res, soft) {
  if (res.error) { sayError(res.error); return; }
  // В ответе только изменённые системы (`changed`) - превью вливает их в
  // свои, весь файл заново не передаётся
  withParticles((w) => w.mergeSystems(res.changed, pSystem, { soft }));
  ensureEffectMaterials();
  setDiff(res.diff);
  fillTree(pcfNodes, pSystem);
  setTitle(pSystem);
  // Значение могло создать модуль - перечитываем, чтобы бледные поля стали
  // обычными, а соседние крутилки показали то, что теперь в файле
  await showParams(pSystem);
}

/** Редактор одного атрибута экспертного режима - по типу из PCF */
export function attrField(attr, onEdit) {
  const box = document.createElement('div');
  box.className = 'params__in';

  // Атрибут с фиксированным набором значений - список, а не голое число
  if (attr.enum) {
    const sel = document.createElement('select');
    sel.className = 'input';
    for (const [v, label] of Object.entries(attr.enum)) sel.append(new Option(label || v, v));
    sel.value = String(attr.v);
    sel.addEventListener('change', () => onEdit(Number(sel.value)));
    box.append(sel);
    return box;
  }

  if (attr.t === 'bool') {
    const i = document.createElement('input');
    i.type = 'checkbox';
    i.checked = Boolean(attr.v);
    i.addEventListener('change', () => onEdit(i.checked));
    box.append(i);
    return box;
  }

  if (attr.t === 'color') {
    // Цвет и прозрачность - разными полями: альфа в PCF четвёртая компонента,
    // а <input type="color"> о ней не знает
    const rgba = attr.v.slice();
    const hex = (n) => Math.max(0, Math.min(255, n | 0)).toString(16).padStart(2, '0');
    const c = document.createElement('input');
    c.type = 'color';
    c.className = 'colorfield';
    c.value = '#' + hex(rgba[0]) + hex(rgba[1]) + hex(rgba[2]);
    const alpha = document.createElement('input');
    alpha.className = 'input input--num input--tiny';
    alpha.type = 'number'; alpha.min = 0; alpha.max = 255; alpha.step = 1;
    alpha.value = rgba[3] ?? 255;
    const push = () => {
      const n = parseInt(c.value.slice(1), 16);
      onEdit([(n >> 16) & 255, (n >> 8) & 255, n & 255, Number(alpha.value)]);
    };
    c.addEventListener('change', push);
    alpha.addEventListener('change', push);
    box.append(c, alpha);
    return box;
  }

  if (attr.t === 'string') {
    const i = document.createElement('input');
    i.className = 'input';
    i.type = 'text';
    i.value = attr.v ?? '';
    i.addEventListener('change', () => onEdit(i.value));
    box.append(i);
    return box;
  }

  if (Array.isArray(attr.v)) {
    // vec2/vec3/vec4 - по полю на компоненту, значение уходит целиком
    const vals = attr.v.slice();
    vals.forEach((v, n) => {
      const i = document.createElement('input');
      i.className = 'input input--num input--tiny';
      i.type = 'number'; i.step = '0.01';
      i.value = v;
      i.addEventListener('change', () => {
        vals[n] = Number(i.value);
        onEdit(vals.slice());
      });
      box.append(i);
    });
    return box;
  }

  const i = document.createElement('input');
  i.className = 'input input--num';
  i.type = 'number';
  i.step = attr.t === 'integer' ? '1' : '0.01';
  // В PCF числа float32, и 0.1 приезжает как 0.10000000149011612. Показываем
  // округлённо: значение в файле не трогаем, пока его не правят
  i.value = attr.t === 'integer' ? attr.v : Number(Number(attr.v).toPrecision(7));
  i.addEventListener('change',
    () => onEdit(attr.t === 'integer' ? parseInt(i.value, 10) : Number(i.value)));
  box.append(i);
  return box;
}

/** Проверка «умеет ли движок этот модуль», либо null - движок ещё молчит */
export function supportedModules() {
  const w = particles();
  if (!w || typeof w.implementedModules !== 'function') return null;
  const impl = w.implementedModules();
  const aliases = impl.aliases || {};
  return (group, fn) => {
    const name = String(fn || '').trim().toLowerCase();
    const real = aliases[name] || name;
    return (impl[group] || []).some((x) => String(x).toLowerCase() === real);
  };
}
