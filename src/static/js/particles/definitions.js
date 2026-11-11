/**
 * Определения систем (systemsJson): что из них нужно странице превью
 *
 * Живая правка ползунком простого режима. Пока тянут ползунок, атрибуты системы меняются прямо в определении, и
 * эффект не начинается заново: инициализаторы и операторы читают атрибуты
 * сами на каждом шаге, а запомненное конструктором экземпляры перечитывают
 * (ParticleSystemInstance.refreshFromDef). Итог правки потом всё равно
 * приходит из Python и сверяется по составу (updateSystems с soft)
 */

/**
 * @param {object} def    определение системы из systemsJson
 * @param {Array}  edits  [{group, index, attr, component, type, value}],
 *                        group null - атрибут самой системы
 */
export function patchDefinition(def, edits) {
  for (const e of edits || []) {
    const holder = e.group ? def[e.group]?.[e.index]?.attrs : def.attrs;
    if (!holder) continue;
    const key = String(e.attr).toLowerCase();
    const a = holder[key] || (holder[key] = { t: e.type, v: null });
    if (e.component === null || e.component === undefined) {
      a.v = e.value;
    } else {
      const v = Array.isArray(a.v) ? a.v.slice() : [0, 0, 0];
      v[e.component] = e.value;
      a.v = v;
    }
  }
}

/** Экземпляры этой системы во всём дереве перечитывают определение */
export function refreshInstances(root, def) {
  if (!root) return;
  if (root.def === def) root.refreshFromDef();
  for (const child of root.children) refreshInstances(child, def);
}

/** Материалы эффекта `root` (с дочерними), которых нет в `materials` */
export function missingMaterials(systems, materials, root) {
  const out = new Set();
  const seen = new Set();
  const stack = [root];
  while (stack.length) {
    const name = stack.pop();
    if (seen.has(name)) continue;
    seen.add(name);
    const def = systems[name];
    if (!def) continue;
    const mat = def.attrs && def.attrs.material && def.attrs.material.v;
    if (mat && !(mat in materials)) out.add(mat);
    for (const child of def.children || []) stack.push(child.childName);
  }
  return [...out];
}

/**
 * Точечная правка из Python поверх уже показанного: определения меняются на
 * месте, чтобы эффект не начинался заново. Значение в кадре и так стоит с
 * ползунка, но в файл оно могло лечь иначе (целое без дроби, цвет в 0-255) -
 * показываем записанное. Возвращает определения, которые надо перечитать
 */
export function adoptDefinitions(systems, changed) {
  const touched = [];
  for (const [name, def] of Object.entries(changed || {})) {
    const cur = systems[name];
    if (cur) {
      Object.assign(cur, def);
      touched.push(cur);
    } else {
      systems[name] = def;
    }
  }
  return touched;
}
