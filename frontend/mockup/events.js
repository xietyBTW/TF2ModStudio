/*
 * События воркеров
 *
 * Порядок важен. У ОДНОМАТЕРИАЛЬНОЙ модели текстура приезжает прямо в
 * model_ready, и события materials не будет вовсе, у многоматериальной
 * materials придёт следом и перепишет альбом.
 */

import * as api from './api.js';
import { say, sayError, sayBusy, withViewer } from './stage.js';
import { notifyApp } from './app-note.js';
import { setBusy, showResult, work } from './layout.js';
import { plural } from './util.js';
import { dockFx } from './buildfx.js';
import { ask } from './ask.js';
import { showReport } from './diagnostics.js';
import { showFailure } from './fail.js';
import { askForModel } from './build.js';
import { showCpModel } from './particles/points.js';
import { refreshWarpaint, recheckWarpaint } from './warpaint.js';
import { t } from './i18n.js';
import {
  refreshView,
  showModel,
  rememberModel,
  lastModel,
  showMaterials,
  showSkins,
  showFirstPerson,
  showFpActions,
  showTauntClasses, showWearSlots, applyFpClip, fpClipArrived,
  showSpecialAnimated,
  specialSceneFailed,
  showSpecialScene,
  showSkybox,
  addFrame,
  setCardTitles,
  showPartsAnimation,
  showDecor,
  festiveFailed,
} from './preview.js';

// События воркеров
// Порядок важен. У ОДНОМАТЕРИАЛЬНОЙ модели текстура приезжает прямо в
// model_ready и события materials не будет вовсе, у многоматериальной
// materials придёт следом и перепишет альбом. Поэтому один кадр - не особый
// случай, а тот же альбом длиной в единицу

api.subscribe((ev) => {
  switch (ev.event) {
    // Ход работы - с задержкой: короткая загрузка успеет закончиться, и
    // подпись не мигнёт (см. sayBusy)
    case 'progress':
      sayBusy(ev.text);
      break;

    case 'model_ready':
      // Альбом наполняется ТОЛЬКО из applyView: два источника расходились -
      // кадр из события затирался пустым состоянием и обратно
      rememberModel(ev);
      // На сцене рук или насмешки обычной модели в кадре нет: своя модель,
      // загруженная оттуда, показалась бы под ригом вида от первого лица.
      // Кадр запомнен - им вернут обычный вид по выходу
      if ((work.dataset.scene || 'item') === 'item') showModel(ev);
      // Модель готова, но в кадре сцена: подпись о её загрузке («Загрузка
      // текстуры…») убирает только показ модели, и без этого она висела бы
      // бесконечно - так было при смене стиля шапки на «На персонаже»
      else say('');
      // War Paint есть не у каждого оружия: кнопка появляется, когда каталог
      // ответит про эту модель
      refreshWarpaint(ev.obj);
      break;

    case 'paintkit_ready':
      // Не собралось - убираем с модели предпросмотр, иначе казалось бы,
      // что War Paint наложен
      if (!ev.ok) { sayError(ev.message || 'War Paint не собрался'); refreshView(); break; }
      // Текстуру Python уже положил на карточку - перечитываем показ целиком
      refreshView();
      say(ev.missing && ev.missing.length
        ? t('В игре нет части текстур War Paint: {}').replace('{}', ev.missing.join(', '))
        : '');
      document.dispatchEvent(new Event('texture:set'));
      break;

    // Материалы, командные текстуры и вариант меняют то, ЧТО показывать.
    // Пересчитывает это Python, поэтому спрашиваем состояние целиком
    case 'materials':
    case 'blu_materials':
    case 'blu_ready':
    case 'australium':
      refreshView();
      break;

    // Гирлянда поверх оружия - своим слоем вьювера, мимо альбома
    case 'festive_decor':
      showDecor(ev);
      break;
    case 'festive_failed':
      festiveFailed();
      break;

    case 'game_integrity':
      integrityNote(ev);
      break;

    case 'animated':
      // Многокадровый VTF: анимацию крутит сам вьювер
      withViewer((w) => w.loadAnimatedTexture(
        ev.frames.map(api.fileUrl), ev.fps, ''));
      showMaterials(['текстура'], { 'текстура': ev.frames[0] });
      break;

    case 'cp_model':
      // Модель для точек частиц разобрана (или не удалась)
      showCpModel(ev);
      break;

    // Кадры гифки с карточки разобраны: они едут в состоянии показа
    case 'texture_animated':
      refreshView();
      break;

    case 'parts_animated':
      // Гифка на части: кадры склейки в уменьшенном размере, крутит вьювер
      showPartsAnimation(ev);
      break;

    case 'render_hints':
      withViewer((w) => w.setMaterialHints(ev.hints));
      break;

    // Ряд стилей рисуем сразу, а показ сверяет его с Python: у своей модели
    // в ряду ещё и Australium, которого в этом событии нет
    case 'skins':
      showSkins(ev.info);
      refreshView();
      break;

    // Вид от первого лица: сцена приходит либо мешем, либо со скелетом.
    // Текстуры к ней приезжают обычным materials, поэтому здесь только меш
    case 'fp_ready':
      showFirstPerson(ev.obj, ev.rig);
      break;

    case 'fp_animated':
      withViewer((w) => {
        // Риг СТРОГО до сцены: applyTransform читает его при показе модели,
        // иначе камера встаёт орбитой и кадр оказывается пустым
        w.setViewRig(ev.rig);
        w.loadViewmodelAnimated(ev.scene, 0);
      });
      fpClipArrived();      // целая сцена - тоже приезд клипа шага
      say('');
      // Текстуры чужого мода воркер не находит: он ищет их в игре по её
      // `$cdmaterials`, а лежат они в VPK человека. Раскладывает их состояние
      // показа - его и перечитываем, иначе мод висит в руке серым
      refreshView();
      break;

    // Какие анимации есть у этого оружия - знает только воркер: список
    // приходит из QC модели, общего перечня не существует.
    // Сменили анимацию у показанной сцены: приехали ТОЛЬКО дорожки
    case 'fp_clip':
      applyFpClip(ev.clip);
      break;

    // Насмешка: сцена та же по устройству, но камера свободная - рига нет
    case 'taunt_animated':
      withViewer((w) => {
        w.setViewRig(null);
        w.loadViewmodelAnimated(ev.scene, 0);
      });
      say('');
      break;

    case 'taunt_classes':
      showTauntClasses(ev.classes);
      break;

    case 'wear_slots':
      showWearSlots(ev);
      break;

    case 'fp_actions':
      showFpActions(ev.actions);
      break;

    case 'fp_editable':
      // Правится только оружие: руки в сцене стоковые и чужие
      withViewer((w) => w.setEditableMeshNames(ev.names));
      break;

    // Спец-режимы: у крита и эффектов смерти своя сцена с персонажем - её
    // строит вьювер
    case 'texture_only':
      showSpecialScene(ev);
      refreshView();
      break;

    // Настоящая сцена спец-режима: солдат умирает нужной смертью. Приходит
    // позже кубиков-заглушки - её надо собрать из модели и анимаций
    case 'special_animated':
      showSpecialAnimated(ev);
      break;

    // Мод из VPK опознан: стало известно, какое оружие он заменяет. Значит
    // его можно посмотреть в руках - открываем вкладку вида от первого лица
    case 'mod_weapon': {
      // Ряд сцен у кадра, а не ряд режимов: `data-scene` есть и у точек
      // эффекта, поэтому ищем в своём ряду
      const tab = document.querySelector('.half__bar--scenes [data-scene="fp"]');
      if (tab) tab.hidden = !ev.ready;
      if (ev.ready) say(`Мод заменяет ${ev.key} - можно посмотреть в руках`);
      // Модель мода уже в кадре, а как её положить, стало ясно только сейчас
      if (ev.pose && lastModel && !lastModel.pose && (work.dataset.scene || 'item') === 'item') {
        rememberModel({ ...lastModel, pose: ev.pose });
        showModel(lastModel);
      }
      // По оружию ищутся War Paint и гирлянды: спрошенные при показе модели
      // ответы были ещё без него
      recheckWarpaint();
      refreshView();
      break;
    }

    case 'skybox':
      // Событие целиком: кроме граней в нём панорама - ей нужна своя карточка
      showSkybox(ev);
      break;

    // Этап двигает линию, подшаг (упаковка, замена модели) только
    // подписывает, что внутри этапа: проценты у него свои
    case 'build_progress':
      setBusy(true);
      if (ev.sub) dockFx.detail(ev.text);
      else dockFx.step(ev.percent, ev.text);
      break;

    // Своя модель подменила основную, а у оружия есть сменная часть
    // (разбитая бутылка, взорванный кабер) - сборка ждёт, чем её собрать
    case 'need_model':
      askForModel(ev.part, ev.kind);
      break;

    // Удача - коротко: имя мода, папку откроет кнопка рядом. Длинное «VPK
    // успешно создан: путь» с предупреждениями в одну строку не влезает;
    // сами предупреждения в журнале, он открывается щелчком по итогу
    case 'build_done': {
      setBusy(false);
      let text = ev.message || (ev.ok ? 'Готово' : 'Ошибка сборки');
      if (ev.ok && ev.filename) {
        text = `Мод собран · ${ev.filename}`;
        if (ev.warnings) {
          text += ' · ' + ev.warnings + ' '
            + plural(ev.warnings, 'предупреждение', 'предупреждения', 'предупреждений');
        }
      }
      dockFx.finish(ev.ok, text, ev.cancelled);
      showResult(ev.ok, !ev.warnings);
      break;
    }

    case 'uv_ready':
      if (!ev.ok || !ev.path) { notifyApp(ev.message || 'UV-шаблон не построен', 'error'); break; }
      // Кладём рядом с текстурами: сравнивать развёртку с текстурой удобнее
      // в одном ряду, чем в отдельном окне.
      // У многоматериальной модели разметок несколько: у каждого материала
      // своя текстура и своя развёртка в тех же координатах
      const uvFiles = (ev.paths && ev.paths.length) ? ev.paths : [ev.path];
      notifyApp(uvFiles.length > 1 ? `UV-шаблоны: ${uvFiles.length} шт.`
                                   : `UV-шаблон: ${uvFiles[0]}`);
      uvFiles.forEach((file, index) => addFrame(
        uvFiles.length > 1 ? `UV-шаблон ${index + 1}` : 'UV-шаблон', file));
      break;

    // Файлы декомпиляции готовы: пока выбор не сделан, за ними числится
    // временная папка - отказ тоже надо отправить, иначе она останется
    case 'extract_files':
      if (!ev.ok) { notifyApp(ev.message || 'Модель не извлечена', 'error'); break; }
      ask({ title: 'Что сохранить в папку экспорта', list: ev.files,
            multi: true, chosen: ev.selected || [], ok: 'Сохранить' })
        .then(async (picked) => {
          const res = await api.exportModelFiles(picked || []);
          if (res.error) notifyApp(res.error, 'error');
          else if (res.cancelled) notifyApp('Извлечение отменено', 'info');
        });
      break;

    // Мод из VPK: карточки строятся из его VTF, а не из материалов игровой
    // модели. Подписи запоминаем - дальше альбом рисуется обычным путём
    case 'mod_cards':
      setCardTitles(Object.fromEntries(
        ev.cards.map((c) => [c.name, c.display_name || c.name])));
      refreshView();
      break;

    // Режим «только геометрия»: модель на экране своя, а карточки игровые -
    // они только что стали известны. Показ берём целиком: прямая заливка
    // игровой текстурой перекрывала правки работы, а карточки оставались
    // пустыми, если прежний запрос показа успел раньше них
    case 'cards_ready':
      refreshView();
      // Здесь эта загрузка кончается: model_ready у неё нет, и «Загрузка
      // текстуры…» иначе висела над кадром до конца сеанса
      say('');
      break;

    case 'diagnostics':
      showReport(ev);
      break;

    case 'tool_done':
      notifyApp(ev.message || (ev.ok ? 'Готово' : 'Не получилось'), ev.ok ? 'done' : 'error');
      break;

    case 'failed':
      withViewer((w) => w.stopLoading());
      // У спец-режима есть запасной кадр: не собралась настоящая сцена -
      // показываем прежнего человечка, а не пустоту с ошибкой
      if (!specialSceneFailed(ev.error)) showFailure(ev);
      break;

    default:
      break;
  }
});

//: Сколько подмен уже показано: событие приходит на каждый файл, а сказать
//: надо один раз и только о новом
let integrityShown = { modified: 0, restored: 0 };
let integrityTimer = 0;

/** Файлы игры переписаны чужой программой (game_integrity в Python).
 *  Восстановленные из проверенной копии - к сведению, без оригинала - совет */
function integrityNote(ev) {
  clearTimeout(integrityTimer);
  integrityTimer = setTimeout(() => {
    const modified = (ev.modified || []).length;
    const restored = (ev.restored || []).length;
    if (modified > integrityShown.modified) {
      notifyApp(`Файлы игры изменены сторонней программой: ${modified} - укажите прелоадер в «Настройках» или проверьте файлы игры в Steam`, 'info');
    } else if (restored > integrityShown.restored && !integrityShown.restored) {
      notifyApp(`Файлы игры изменены прелоадером - взяты оригиналы из его копии: ${restored}`, 'info');
    }
    integrityShown = { modified, restored };
  }, 400);
}
