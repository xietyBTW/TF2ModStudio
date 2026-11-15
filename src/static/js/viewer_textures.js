/*
 * Текстуры модели во вьювере: память видеокарты и повторная раздача
 *
 * three.js память видеокарты сам не отдаёт: текстура 2048 с мипами держит
 * около 22 МБ, пока её не освободят. Материалы при этом не трогаем: с ними
 * уходит шейдер, и следующая модель собирала бы его заново. Освобождённое по
 * ошибке не ломается, three зальёт его снова при первом показе.
 *
 * Страница после каждого события раздаёт весь набор текстур заново, и грузить
 * ту же картинку второй раз незачем: 2048 - это разбор PNG и заливка в
 * видеокарту. Пропускается только адрес с версией файла (`&v=`): без неё
 * картинку могли переписать на месте под тем же путём.
 *
 * Здесь нет ни сцены, ни three.js: функции получают объекты и зовут у них
 * traverse и dispose, поэтому проверяются через Node.
 */

/** Текстуры (map) всех материалов под `root` */
export function mapsOf(root, into = new Set()) {
  if (root) root.traverse(o => {
    for (const m of [].concat(o.material || [])) if (m && m.map) into.add(m.map);
  });
  return into;
}

/** Геометрия и текстуры объекта, снятого со сцены. `foreign(tex)` - текстуры
 *  с чужим хозяином (гирлянда), у них своя чистка */
export function freeObject(root, foreign = () => false) {
  root.traverse(o => { if (o.geometry) o.geometry.dispose(); });
  mapsOf(root).forEach(tex => { if (!foreign(tex)) tex.dispose(); });
}

/** Освобождает те из `maps`, которых нет ни на модели, ни в запасе `kept` */
export function retireMaps(maps, root, kept = [], foreign = () => false) {
  const used = mapsOf(root, new Set(kept));
  for (const tex of maps) {
    if (tex && !used.has(tex) && !foreign(tex)) tex.dispose();
  }
}

export function hasVersion(url) { return String(url).includes('&v='); }

/**
 * Текстура с этим адресом, если она уже на всех мешах, отобранных `pick`
 *
 * `aside(name)` - материалы, на которые текстуры предмета не ложатся
 * (гирлянда, призрак): в счёт они не идут
 */
export function alreadyOn(root, url, pick, aside = () => false) {
  if (!root || !hasVersion(url)) return null;
  let on = null, same = true;
  root.traverse(child => {
    if (!child.isMesh || !child.material || Array.isArray(child.material)) return;
    if (aside(String(child.material.name || '')) || !pick(child)) return;
    const map = child.material.map;
    if (map && map.userData.url === url) on = map;
    else same = false;
  });
  return same ? on : null;
}
