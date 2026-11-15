/*
 * Огонь горящего игрока поверх его раскраски
 *
 * В игре это не отдельная текстура тела, а слой `$detail` в материалах
 * игроков, шапок и оружия: мелкая плитка, которую шейдер ПРИБАВЛЯЕТ к уже
 * освещённому цвету (`$detailblendmode 6`), а прокси листает её кадры. У
 * three.js так работает `emissiveMap`: своя развёртка с повтором и сложение
 * после освещения.
 *
 * Сила слоя в игре не постоянна (прокси BurnLevel): вспышка за 0,3 с и
 * угасание до нуля к десятой секунде. Угасает огонь не равномерно, а
 * порогом: сперва пропадают тёмные места текстуры, яркие держатся дольше.
 * Формула взята из шейдера игры (TextureCombinePostLighting, режим 6).
 *
 * Материалы во вьювере пересоздаются на каждую смену текстуры, поэтому слой
 * вешается не один раз, а в `makeMeshMaterial` (`wear`).
 *
 * Здесь нет сцены: кто рисует и какие материалы сейчас в кадре, говорит
 * вьювер (`each`, `requestRender`), поэтому расчёты проверяются в Node.
 */

//: Сколько секунд горит игрок (TF_BURNING_FLAME_LIFE) и за сколько огонь
//: набирает силу. По истечении превью поджигает солдата заново
export const BURN_SECONDS = 10;
export const BURN_PEAK = 0.3;

/** Прямоугольники кадров на листе: [x, y, ширина, высота] по порядку кадров */
export function atlasCells(width, height, cols, rows, count) {
  const w = Math.floor(width / cols), h = Math.floor(height / rows);
  const cells = [];
  for (let i = 0; i < count && i < cols * rows; i++) {
    cells.push([(i % cols) * w, Math.floor(i / cols) * h, w, h]);
  }
  return cells;
}

/** Кадр по времени: по кругу, как прокси AnimatedTexture */
export function frameAt(seconds, fps, count) {
  if (!(count > 0)) return 0;
  return Math.floor(Math.max(0, seconds) * Math.max(0, fps)) % count;
}

/** Сила огня от 0 до 1 через `seconds` после поджога, по кругу */
export function burnLevel(seconds) {
  const t = ((seconds % BURN_SECONDS) + BURN_SECONDS) % BURN_SECONDS;
  if (t < BURN_PEAK) return t / BURN_PEAK;
  return 1 - (t - BURN_PEAK) / (BURN_SECONDS - BURN_PEAK);
}

/** Что прибавится к цвету при яркости текстуры `detail` и силе огня `level` */
export function thresholdFade(detail, level) {
  const mult = level >= 0.5 ? 1 / level : 4 * level;
  const add = level >= 0.5 ? 1 - mult : -0.5 * mult;
  return Math.min(1, Math.max(0, mult * detail + add));
}

//: То же, что thresholdFade, для шейдера three.js: вместо умножения свечения
//: на карту - сложение с порогом
const SHADER_FROM = '#include <emissivemap_fragment>';
const SHADER_TO = `#ifdef USE_EMISSIVEMAP
	vec4 emissiveColor = texture2D( emissiveMap, vEmissiveMapUv );
	float fireMult = fireBurn >= 0.5 ? 1.0 / fireBurn : 4.0 * fireBurn;
	float fireAdd = fireBurn >= 0.5 ? 1.0 - fireMult : -0.5 * fireMult;
	totalEmissiveRadiance = clamp( fireMult * emissiveColor.rgb + fireAdd, 0.0, 1.0 );
#endif`;

/**
 * Слой огня. `each(fn)` обходит материалы модели в кадре.
 *
 * set(spec): {atlas, cols, rows, count} - лист кадров игры, либо {frames:
 * [url]} - своя картинка; у обоих fps и scale. null - убрать слой
 */
export function createFire(THREE, { each, requestRender }) {
  let frames = [];
  let timer = null;
  let started = 0;
  let fps = 0;
  let generation = 0;
  //: Одна сила огня на все материалы сцены
  const burn = { value: 0 };

  const compile = (shader) => {
    shader.uniforms.fireBurn = burn;
    shader.fragmentShader = 'uniform float fireBurn;\n'
      + shader.fragmentShader.replace(SHADER_FROM, SHADER_TO);
  };

  const tune = (tex, scale) => {
    tex.colorSpace = THREE.SRGBColorSpace;
    tex.wrapS = tex.wrapT = THREE.RepeatWrapping;
    tex.repeat.set(scale, scale);
    return tex;
  };

  const seconds = () => (performance.now() - started) / 1000;
  const current = () => frames[frameAt(seconds(), fps, frames.length)];

  const wear = (material) => {
    if (!material || Array.isArray(material) || !material.emissive) return material;
    const tex = frames.length ? current() : null;
    if (material.emissiveMap === tex) return material;
    // Смена «есть слой - нет слоя» меняет шейдер, смена кадра - нет
    if (!material.emissiveMap !== !tex) {
      material.onBeforeCompile = tex ? compile : () => {};
      material.emissive.setScalar(tex ? 1 : 0);
      material.needsUpdate = true;
    }
    material.emissiveMap = tex;
    return material;
  };

  const paint = () => {
    burn.value = frames.length ? burnLevel(seconds()) : 0;
    each(wear);
    requestRender();
  };

  const stop = () => {
    generation++;
    if (timer !== null) { clearInterval(timer); timer = null; }
    frames.forEach((tex) => tex.dispose());
    frames = [];
  };

  const start = (textures, rate) => {
    frames = textures;
    fps = rate;
    started = performance.now();
    paint();
    // Таймер нужен и одному кадру: сила огня меняется со временем
    if (frames.length) timer = setInterval(paint, 33);
  };

  const image = (url) => new Promise((resolve, reject) => {
    const img = new Image();
    img.onload = () => resolve(img);
    img.onerror = () => reject(new Error('fire image: ' + url));
    img.src = url;
  });

  const set = async (spec) => {
    stop();
    paint();                       // прежний слой снят сразу, не после загрузки
    if (!spec) return;
    const mine = generation;
    const scale = spec.scale || 1;
    let textures = [];
    try {
      if (spec.atlas) {
        const sheet = await image(spec.atlas);
        textures = atlasCells(sheet.width, sheet.height, spec.cols, spec.rows, spec.count)
          .map(([x, y, w, h]) => {
            const canvas = document.createElement('canvas');
            canvas.width = w;
            canvas.height = h;
            canvas.getContext('2d').drawImage(sheet, x, y, w, h, 0, 0, w, h);
            return tune(new THREE.CanvasTexture(canvas), scale);
          });
      } else {
        const loaded = await Promise.all((spec.frames || []).map(image));
        textures = loaded.map((img) => {
          const tex = tune(new THREE.Texture(img), scale);
          tex.needsUpdate = true;
          return tex;
        });
      }
    } catch (err) {
      console.warn('[3D viewer] fire overlay:', err);
    }
    // Пока грузилось, слой сменили или сняли
    if (mine !== generation) { textures.forEach((tex) => tex.dispose()); return; }
    start(textures, spec.fps || 0);
  };

  return { set, wear, active: () => frames.length > 0, level: () => burn.value };
}
