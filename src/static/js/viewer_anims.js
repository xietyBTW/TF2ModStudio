/*
 * Анимации текстур во вьювере: гифка на материале крутится списком кадров
 *
 * На модели их несколько сразу: у каждого материала своя, со своей частотой.
 * Имя '' - анимация на все меши: она красит и чужие материалы, поэтому с
 * именными не живёт
 *
 * Здесь нет ни сцены, ни three.js: кадр на меши кладёт `apply`, текстуры
 * отпускает `retire`, таймер приходит снаружи, поэтому проверяется через Node
 */

export function createAnims({ apply, retire,
                              every = (fn, ms) => setInterval(fn, ms),
                              cancel = (id) => clearInterval(id) }) {
  //: имя меша или материала -> {key, frames, timer}
  const live = new Map();

  function stop(name) {
    const anim = live.get(name);
    if (!anim) return;
    // Сначала из списка: кадры остальных анимаций retire трогать не должен,
    // а свои - уже может
    live.delete(name);
    if (anim.timer !== null) cancel(anim.timer);
    retire(anim.frames);
  }

  function stopAll() { [...live.keys()].forEach(stop); }

  /**
   * Занимает имя под анимацию. null - такая же уже идёт или грузится
   *
   * `frames` - массив, который вызывающий заполняет по мере загрузки: так
   * оборванная на полпути загрузка отдаёт и то, что успело приехать
   */
  function claim(name, key, frames) {
    const was = live.get(name);
    if (was && was.key === key) return null;
    if (name === '') stopAll();
    else { stop(''); stop(name); }
    const anim = { key, frames, timer: null };
    live.set(name, anim);
    return anim;
  }

  const owns = (name, anim) => live.get(name) === anim;

  /** Кадры загружены: крутим. Имя уже отдано другой анимации - молчим */
  function start(name, anim, fps) {
    if (!owns(name, anim) || anim.timer !== null) return;
    let frame = 0;
    const ms = Math.max(16, Math.round(1000 / Math.max(0.1, fps)));
    anim.timer = every(() => {
      apply(name, anim.frames[frame % anim.frames.length]);
      frame++;
    }, ms);
  }

  return {
    claim, start, stop, stopAll, owns,
    /** Крутится ли что-то на этом имени - своя анимация или общая */
    covers: (name) => live.has('') || live.has(name),
    /** Кадры всех анимаций: их нельзя отпускать, пока они в работе */
    frames: () => [...live.values()].flatMap((anim) => anim.frames),
  };
}
