/*
 * Анимации от первого лица группами
 *
 * Воркер отдаёт сырые действия (weapon_anim_catalog.Action): IDLE, DRAW,
 * RELOAD_START, RELOAD, RELOAD_FINISH, INSPECT_START… Десять кнопок с такими
 * именами под кадром читались плохо, а перезарядку человек хочет увидеть
 * целиком, не её начало отдельно. Поэтому кнопка - группа, и группа из
 * нескольких действий играется цепочкой, как в игре. Что в группы не попало
 * (HOLSTER, ALT_FIRE, CRIT), остаётся в списке «Все анимации»
 */

//: Подпись группы и её действия в порядке проигрывания
const GROUPS = [
  ['Покой', ['IDLE']],
  ['Достать', ['DRAW']],
  ['Выстрел', ['FIRE']],
  ['Перезарядка', ['RELOAD_START', 'RELOAD', 'RELOAD_FINISH']],
  ['Осмотр', ['INSPECT_START', 'INSPECT_IDLE', 'INSPECT_END']],
];

/**
 * Группы из того, что есть у оружия: { groups: [{label, chain}], rest }.
 * Группа без единого действия пропадает, у неполной цепочка короче
 */
export function fpGroups(actions) {
  const list = actions || [];
  const have = new Set(list);
  const groups = GROUPS
    .map(([label, chain]) => ({ label, chain: chain.filter((a) => have.has(a)) }))
    .filter((g) => g.chain.length);
  const used = new Set(groups.flatMap((g) => g.chain));
  return { groups, rest: list.filter((a) => !used.has(a)) };
}

/** Доля проигранного всей цепочкой: шаг `step` из `count`, внутри шага `p` */
export function chainProgress(step, count, p) {
  return count > 0 ? Math.min(1, (step + (p || 0)) / count) : 0;
}

/**
 * Пора ли переходить к следующему шагу цепочки: клип у самого конца (ловим до
 * повтора, чтобы не мелькнуло начало) или уже доиграл хоть раз - вьювер
 * считает круги сам (viewmodelLoops), и редкие кадры конец не пропустят
 */
export function stepDone(p, loops) {
  return (loops ?? 0) > 0 || (p !== null && p !== undefined && p > 0.97);
}
