// Опора гизмо подгонки - центр геометрии, а не ноль модели
//
// Числа подгонки остаются вокруг нуля (их так запекает Python), но у модели
// «из интернета» ноль бывает далеко от неё: после автоподгонки гизмо висело
// в воздухе рядом с катаной. Гизмо держит невидимую опору в центре, а узел
// (группа своей модели или гирлянда) пересчитывается от неё так, чтобы центр
// оставался под опорой

// Числа подгонки (масштаб, поворот X -> Y -> Z, сдвиг) живут в осях SMD,
// узел - в осях сцены: (x, y, z) -> (x, z, −y), как в SmdToObjService
function axes(THREE) {
  const c = new THREE.Matrix4().set(1, 0, 0, 0,  0, 0, 1, 0,  0, -1, 0, 0,  0, 0, 0, 1);
  return [c, c.clone().transpose()];
}

/** Числа подгонки в осях SMD -> положение узла в осях сцены */
export function fitPose(THREE, scale, rotate, offset) {
  const [c, ct] = axes(THREE);
  const d = Math.PI / 180;
  const r = new THREE.Matrix4().makeRotationZ(rotate[2] * d)
    .multiply(new THREE.Matrix4().makeRotationY(rotate[1] * d))
    .multiply(new THREE.Matrix4().makeRotationX(rotate[0] * d));
  return { quat: new THREE.Quaternion().setFromRotationMatrix(c.multiply(r).multiply(ct)),
           scale, pos: new THREE.Vector3(offset[0], offset[2], -offset[1]) };
}

/** Обратно: трансформ узла -> числа подгонки в осях SMD */
export function fitFromNode(THREE, node) {
  const [c, ct] = axes(THREE);
  // Масштаб только равномерный: сборке нужен один множитель
  const s = (node.scale.x + node.scale.y + node.scale.z) / 3;
  node.scale.setScalar(s);
  const m = ct.multiply(new THREE.Matrix4().makeRotationFromQuaternion(node.quaternion)).multiply(c);
  // Fit.matrix() у Python - Rz·Ry·Rx, у THREE это порядок 'ZYX'
  const e = new THREE.Euler().setFromRotationMatrix(m, 'ZYX');
  const deg = (v) => Math.round(v * 180 / Math.PI * 10) / 10;
  const r1 = (v) => Math.round(v * 10) / 10;
  const p = node.position;
  return { scale: Math.round(s * 1000) / 1000,
           rotate: [deg(e.x), deg(e.y), deg(e.z)],
           offset: [r1(p.x), r1(-p.z), r1(p.y)] };
}

/**
 * Сдвиг в мировых осях -> сдвиг в осях родителя узла
 *
 * Узел подгонки (своя модель, гирлянда) вложен в модель предмета, а её
 * вьювер кладёт набок (js/viewer_lay.js): мировой сдвиг мыши без поворота
 * родителя уводил бы узел не туда
 */
export function vectorInParent(THREE, parent, v) {
  const q = parent.getWorldQuaternion(new THREE.Quaternion()).invert();
  const s = parent.getWorldScale(new THREE.Vector3()).x || 1;
  return v.clone().applyQuaternion(q).divideScalar(s);
}

/** Поворот вокруг мировой оси -> тот же поворот в осях родителя узла */
export function quatInParent(THREE, parent, q) {
  const p = parent.getWorldQuaternion(new THREE.Quaternion());
  return p.clone().invert().multiply(q).multiply(p);
}

export function createFitPivot(THREE) {
  const object = new THREE.Object3D();
  object.name = 'fit-pivot';

  /** Центр габаритов узла в его собственных осях (кэш на узле) */
  function center(node) {
    if (node.userData.fitCenter) return node.userData.fitCenter;
    node.updateMatrixWorld(true);
    const box = new THREE.Box3().setFromObject(node);
    const c = box.isEmpty() ? new THREE.Vector3()
      : node.worldToLocal(box.getCenter(new THREE.Vector3()));
    node.userData.fitCenter = c;
    return c;
  }

  /** Где центр узла в осях его родителя при данном повороте и масштабе */
  function centerIn(node, quat, scale) {
    return center(node).clone().multiplyScalar(scale).applyQuaternion(quat);
  }

  return {
    object,
    centerIn,
    /** Центр узла в мировых осях - точка опоры для G/R/S */
    centerWorld(node) {
      node.updateMatrixWorld(true);
      return node.localToWorld(center(node).clone());
    },
    /** Опора встаёт на центр узла и повторяет его поворот и масштаб */
    sync(node) {
      if (!node) return;
      if (object.parent !== node.parent && node.parent) node.parent.add(object);
      object.quaternion.copy(node.quaternion);
      object.scale.copy(node.scale);
      object.position.copy(node.position).add(centerIn(node, node.quaternion, node.scale.x));
    },
    /** Гизмо сдвинули - узел встаёт так, чтобы центр остался под опорой */
    apply(node) {
      const s = (object.scale.x + object.scale.y + object.scale.z) / 3;
      object.scale.setScalar(s);
      node.quaternion.copy(object.quaternion);
      node.scale.setScalar(s);
      node.position.copy(object.position).sub(centerIn(node, object.quaternion, s));
    },
  };
}
