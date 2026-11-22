/*
 * Инспектор материалов - значок в правом верхнем углу кадра
 *
 * Наведение на модель показывает материал под курсором (имя, текстура,
 * размер, своя или игровая), щелчок открывает его карточку в альбоме: так не
 * надо листать альбом, чтобы найти, какая карточка отвечает за линзу. Подсказку
 * рисует вьювер, страница говорит ему, где своё (setInspectOwn), и слушает
 * щелчок (onInspectPick)
 */

import { withViewer } from './stage.js';
import { showMaterial } from './album.js';

const btn = document.getElementById('inspectbtn');
let on = false;
let view = null;

/** Карточка меша `mesh` по связке из показа (card_scene) */
export function cardOfMesh(st, mesh) {
  for (const [card, meshes] of Object.entries(st?.card_scene || {})) {
    if ((meshes || []).includes(mesh)) return card;
  }
  if (st?.textures && mesh in st.textures) return mesh;       // материал части
  const mats = st?.materials || [];
  return mats.length === 1 ? mats[0] : null;                 // одноматериальная
}

/** Меши, где лежит своё: {карточки своих} -> имена мешей; '*' - все сразу */
export function ownMeshes(st) {
  const own = st?.own_cards || [];
  if ((st?.materials || []).length === 1 && own.includes(st.materials[0])) return ['*'];
  return own.flatMap((card) => (st.card_scene || {})[card] || [card]);
}

function bind(w) {
  w.onInspectPick = (mesh) => {
    const card = cardOfMesh(view, mesh);
    if (card) showMaterial(card);
  };
  // Вьювер гасит инспектор сам, когда модели не стало
  w.onInspectMode = (state) => { on = state; btn.classList.toggle('is-active', state); };
  w.setInspectOwn?.(ownMeshes(view));
}

/** Каждый показ: где своё и есть ли что осматривать */
export function syncInspect(st, hasModel) {
  view = st;
  btn.hidden = !hasModel;
  if (!hasModel && on) setInspect(false);
  withViewer(bind);
}

export function setInspect(state) {
  on = Boolean(state);
  btn.classList.toggle('is-active', on);
  withViewer((w) => { bind(w); w.setInspectMode?.(on); });
}

btn.addEventListener('click', () => setInspect(!on));
// Подгонка и части ловят мышь в кадре сами - инспектор им не мешает
document.addEventListener('fit:changed', () => { if (on) setInspect(false); });
document.addEventListener('parts:changed', () => { if (on) setInspect(false); });
