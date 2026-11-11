"""
Схема простого режима редактора частиц: какие крутилки есть и куда пишут

Новая крутилка = одна запись здесь + переводы particles_sp_<key> и
particles_sp_<key>_tip (ru и en) в translations.py

Состав выбран по срезу стоковых PCF игры (134 файла, 10626 систем): сюда
попало то, что встречается в тысячах систем и что человек без знания
модулей Source назовёт своими словами («закрутка», «цвет к концу жизни»).
Мягкая граница ≈ 99-й процентиль стока, жёсткая - с запасом над максимумом,
умолчание - как в Source

Разделы (`group`) идут в порядке, в котором об эффекте думают: где и сколько
рождается, как летит, что на него действует, какой он, как выглядит
"""

from typing import Tuple

from src.services.simple_params import (
    CURVE_SIGNED_SQRT, CURVE_SQRT, SimpleParam, _r, _v,
)

#: Быстрые правки всего эффекта (см. SimpleParam.scales): масштаб - размеры
#: и расстояния, плотность - число частиц, темп - время (быстрее = меньше
#: секунд, больше скоростей, ускорения - в квадрате)
SCALE = "scale"
DENSITY = "density"
TEMPO = "tempo"

_SPRITES = "render_animated_sprites"
_TRAIL = "render_sprite_trail"
_OFFSET = "Position Modify Offset Random"
_VELOCITY = "Velocity Random"

SIMPLE_PARAMS: Tuple[SimpleParam, ...] = (
    # Рождение. Эмиттеры только правятся: добавленный эмиттер может задвоить
    # залп, поэтому creatable=False
    SimpleParam("spawn_rate", "value",
                (_v(_r("emitters", "emit_continuously", "emission_rate")),),
                minimum=0, maximum=500, hard_max=1e6, curve=CURVE_SQRT,
                default=100, creatable=False, group="birth", unit="per_s",
                scales=((DENSITY, 1), (TEMPO, 1))),
    SimpleParam("spawn_burst", "value",
                (_v(_r("emitters", "emit_instantaneously", "num_to_emit",
                       "integer")),),
                minimum=0, maximum=1000, hard_max=1e6, curve=CURVE_SQRT,
                decimals=0, default=100, creatable=False, group="birth",
                scales=((DENSITY, 1),)),
    # Частицы, которые система выпускает в самый момент старта, сверх
    # эмиттеров: 4000 систем стока держат атрибут, у 250 он не ноль
    SimpleParam("initial_particles", "value",
                (_v(_r(None, "", "initial_particles", "integer")),),
                minimum=0, maximum=500, hard_max=1e6, curve=CURVE_SQRT,
                decimals=0, group="birth", scales=((DENSITY, 1),)),
    # Задержка старта эмиссии - есть у обоих эмиттеров, имя атрибута одно
    SimpleParam("emit_delay", "value",
                (_v(_r("emitters", "emit_continuously", "emission_start_time")),
                 _v(_r("emitters", "emit_instantaneously",
                       "emission_start_time"))),
                minimum=0, maximum=10, hard_max=1e5, curve=CURVE_SQRT,
                creatable=False, group="birth", unit="s",
                scales=((TEMPO, -1),)),
    # Длительность эмиссии; 0 = бесконечно (так в игре)
    SimpleParam("emit_duration", "value",
                (_v(_r("emitters", "emit_continuously", "emission_duration")),),
                minimum=0, maximum=10, hard_max=1e5, curve=CURVE_SQRT,
                creatable=False, group="birth", unit="s",
                scales=((TEMPO, -1),)),
    SimpleParam("max_particles", "value",
                (_v(_r(None, "", "max_particles", "integer")),),
                minimum=1, maximum=5000, hard_max=1e6, curve=CURVE_SQRT,
                decimals=0, default=1000, group="birth",
                scales=((DENSITY, 1),)),
    SimpleParam("lifetime", "range",
                (_v(_r("initializers", "Lifetime Random", "lifetime_min"),
                    _r("initializers", "Lifetime Random", "lifetime_max")),),
                minimum=0.05, maximum=30, hard_min=0, hard_max=1e10,
                curve=CURVE_SQRT, default=0.5, group="birth", unit="s",
                scales=((TEMPO, -1),)),

    # Движение
    # Сферическая область - самая ходовая (7032 модуля в стоке), у неё гизмо
    # в 3D-превью
    SimpleParam("spawn_area", "range",
                (_v(_r("initializers", "Position Within Sphere Random",
                       "distance_min"),
                    _r("initializers", "Position Within Sphere Random",
                       "distance_max")),),
                minimum=0, maximum=500, hard_max=1e5, curve=CURVE_SQRT,
                creatable=False, group="motion", unit="u",
                scales=((SCALE, 1),)),
    # Подъём точки рождения: 5249 модулей, почти всегда сдвиг только по Z
    SimpleParam("spawn_lift", "range",
                (_v(_r("initializers", _OFFSET, "offset min", "vec3", 2),
                    _r("initializers", _OFFSET, "offset max", "vec3", 2)),),
                minimum=-200, maximum=200, hard_min=-1e5, hard_max=1e5,
                curve=CURVE_SIGNED_SQRT, group="motion", unit="u",
                scales=((SCALE, 1),),
                seed=(("initializers", _OFFSET, "offset in local space 0/1",
                       "bool", False),
                      ("initializers", _OFFSET, "control_point_number",
                       "integer", 0),
                      ("initializers", _OFFSET, "offset min", "vec3",
                       (0.0, 0.0, 0.0)),
                      ("initializers", _OFFSET, "offset max", "vec3",
                       (0.0, 0.0, 0.0)))),
    # Скорость: в сферическом инициализаторе либо в отдельном Velocity Random
    SimpleParam("speed", "range",
                (_v(_r("initializers", "Position Within Sphere Random",
                       "speed_min"),
                    _r("initializers", "Position Within Sphere Random",
                       "speed_max")),
                 _v(_r("initializers", _VELOCITY, "speed_min"),
                    _r("initializers", _VELOCITY, "speed_max"))),
                minimum=0, maximum=2000, hard_max=1e5, curve=CURVE_SQRT,
                creatable=False, group="motion", unit="u_s",
                scales=((SCALE, 1), (TEMPO, 1))),
    # Струя вверх (или вниз): скорость по оси Z точки эффекта
    SimpleParam("speed_up", "range",
                (_v(_r("initializers", _VELOCITY,
                       "speed_in_local_coordinate_system_min", "vec3", 2),
                    _r("initializers", _VELOCITY,
                       "speed_in_local_coordinate_system_max", "vec3", 2)),),
                minimum=-1000, maximum=1000, hard_min=-1e5, hard_max=1e5,
                curve=CURVE_SIGNED_SQRT, group="motion", unit="u_s",
                scales=((SCALE, 1), (TEMPO, 1)),
                seed=(("initializers", _VELOCITY, "random_speed_min", "float", 0.0),
                      ("initializers", _VELOCITY, "random_speed_max", "float", 0.0),
                      ("initializers", _VELOCITY, "control_point_number",
                       "integer", 0),
                      ("initializers", _VELOCITY,
                       "speed_in_local_coordinate_system_min", "vec3",
                       (0.0, 0.0, 0.0)),
                      ("initializers", _VELOCITY,
                       "speed_in_local_coordinate_system_max", "vec3",
                       (0.0, 0.0, 0.0)))),
    SimpleParam("gravity", "value",
                (_v(_r("operators", "Movement Basic", "gravity", "vec3",
                       component=2)),),
                minimum=-800, maximum=800, hard_min=-1e6, hard_max=1e6,
                curve=CURVE_SIGNED_SQRT, group="motion", unit="u_s2",
                scales=((SCALE, 1), (TEMPO, 2))),
    # Сопротивление среды: 0 - движение по инерции, 1 - мгновенная остановка
    SimpleParam("drag", "value",
                (_v(_r("operators", "Movement Basic", "drag")),),
                minimum=0, maximum=1, hard_min=-10, hard_max=10, decimals=3,
                group="motion"),
    # Частицы едут за источником (6607 систем стока). Без модуля они остаются
    # там, где родились: у шапки на бегущем игроке - шлейф позади
    SimpleParam("follow", "module",
                (_v(_r("operators", "Movement Lock to Control Point",
                       "control_point_number", "integer")),),
                group="motion",
                seed=(("operators", "Movement Lock to Control Point",
                       "control_point_number", "integer", 0),)),

    # Силы: действуют на частицу всю её жизнь, в отличие от стартовой скорости
    # Хаотичная сила по всем осям: «от» - та же сила с минусом
    SimpleParam("turbulence", "value",
                (_v(*(_r("forces", "random force", "max force", "vec3", i)
                      for i in range(3)),
                    *(_r("forces", "random force", "min force", "vec3", i, -1.0)
                      for i in range(3))),),
                minimum=0, maximum=1000, hard_max=1e6, curve=CURVE_SQRT,
                group="forces", unit="u_s2", scales=((SCALE, 1), (TEMPO, 2))),
    # Притяжение к точке эффекта; минус - отталкивание
    SimpleParam("pull", "value",
                (_v(_r("forces", "Pull towards control point", "amount of force")),),
                minimum=-500, maximum=500, hard_min=-1e6, hard_max=1e6,
                curve=CURVE_SIGNED_SQRT, group="forces",
                scales=((SCALE, 1), (TEMPO, 2)),
                seed=(("forces", "Pull towards control point",
                       "control point number", "integer", 0),
                      ("forces", "Pull towards control point",
                       "falloff power", "float", 0.0))),
    # Закрутка вокруг вертикали; минус - в другую сторону
    SimpleParam("twist", "value",
                (_v(_r("forces", "twist around axis", "amount of force")),),
                minimum=-2000, maximum=2000, hard_min=-1e6, hard_max=1e6,
                curve=CURVE_SIGNED_SQRT, group="forces",
                scales=((SCALE, 1), (TEMPO, 2)),
                seed=(("forces", "twist around axis", "twist axis", "vec3",
                       (0.0, 0.0, 1.0)),
                      ("forces", "twist around axis",
                       "object local space axis 0/1", "bool", False))),

    # Размер
    SimpleParam("size", "value",
                (_v(_r(None, "", "radius")),),
                minimum=0.1, maximum=200, hard_min=0, hard_max=1e5,
                curve=CURVE_SQRT, default=5.0, group="size", unit="u",
                scales=((SCALE, 1),)),
    SimpleParam("size_range", "range",
                (_v(_r("initializers", "Radius Random", "radius_min"),
                    _r("initializers", "Radius Random", "radius_max")),),
                minimum=0.1, maximum=200, hard_min=0, hard_max=1e5,
                curve=CURVE_SQRT, default=5.0, group="size", unit="u",
                scales=((SCALE, 1),)),
    # Рост/усадка за жизнь частицы: 7262 модуля в стоке. Концы независимы -
    # частица может и усыхать
    SimpleParam("size_scale", "range",
                (_v(_r("operators", "Radius Scale", "radius_start_scale"),
                    _r("operators", "Radius Scale", "radius_end_scale")),),
                minimum=0, maximum=10, hard_max=1e4, curve=CURVE_SQRT,
                default=1.0, group="size", ordered=False, unit="x"),

    # Вращение
    # Случайный начальный поворот спрайта: 5154 модуля, чаще всего 0..360 -
    # дым и искры без него выглядят штампованными
    SimpleParam("rotation_start", "range",
                (_v(_r("initializers", "Rotation Random", "rotation_offset_min"),
                    _r("initializers", "Rotation Random", "rotation_offset_max")),),
                minimum=-360, maximum=360, hard_min=-1e5, hard_max=1e5,
                decimals=0, group="rotation", unit="deg"),
    SimpleParam("spin", "value",
                (_v(_r("operators", "Rotation Spin Roll", "spin_rate_degrees",
                       "integer")),),
                minimum=-1000, maximum=1000, hard_min=-1e6, hard_max=1e6,
                curve=CURVE_SIGNED_SQRT, decimals=0, group="rotation",
                unit="deg_s", scales=((TEMPO, 1),)),

    # Цвет и прозрачность
    SimpleParam("colors", "color_pair",
                (_v(_r("initializers", "Color Random", "color1", "color"),
                    _r("initializers", "Color Random", "color2", "color")),),
                group="color"),
    # Цвет, к которому частица приходит к концу жизни: 3910 модулей Color Fade
    SimpleParam("color_end", "color",
                (_v(_r("operators", "Color Fade", "color_fade", "color")),),
                group="color"),
    # Когда идёт перекраска - доля жизни частицы, показываем процентами
    SimpleParam("color_fade_time", "range",
                (_v(_r("operators", "Color Fade", "fade_start_time", scale=0.01),
                    _r("operators", "Color Fade", "fade_end_time", scale=0.01)),),
                minimum=0, maximum=100, decimals=0, default=0, group="color",
                unit="pct",
                seed=(("operators", "Color Fade", "fade_start_time", "float", 0.0),
                      ("operators", "Color Fade", "fade_end_time", "float", 1.0))),
    # Стартовая прозрачность 0-255: 7449 модулей в стоке
    SimpleParam("alpha", "range",
                (_v(_r("initializers", "Alpha Random", "alpha_min", "integer"),
                    _r("initializers", "Alpha Random", "alpha_max", "integer")),),
                minimum=0, maximum=255, decimals=0, default=255, group="color"),
    SimpleParam("fade_in", "range",
                (_v(_r("operators", "Alpha Fade In Random", "fade in time min"),
                    _r("operators", "Alpha Fade In Random", "fade in time max")),),
                minimum=0, maximum=10, hard_max=1e4, default=0.25,
                group="color", unit="s", scales=((TEMPO, -1),)),
    SimpleParam("fade_out", "range",
                (_v(_r("operators", "Alpha Fade Out Random", "fade out time min"),
                    _r("operators", "Alpha Fade Out Random",
                       "fade out time max")),),
                minimum=0, maximum=10, hard_max=1e4, default=0.25,
                group="color", unit="s", scales=((TEMPO, -1),)),

    # Спрайт: как рисуется картинка частицы. Рендерер не создаём - он у
    # системы один, и второй нарисовал бы её дважды
    SimpleParam("orientation", "choice",
                (_v(_r("renderers", _SPRITES, "orientation_type", "integer")),),
                choices=(0, 1, 2, 3), creatable=False, group="sprite"),
    SimpleParam("anim_rate", "value",
                (_v(_r("renderers", _SPRITES, "animation rate")),
                 _v(_r("renderers", _TRAIL, "animation rate"))),
                minimum=0, maximum=60, hard_max=1e4, curve=CURVE_SQRT,
                default=0.1, creatable=False, group="sprite",
                scales=((TEMPO, 1),)),
    SimpleParam("anim_fit", "bool",
                (_v(_r("renderers", _SPRITES, "animation_fit_lifetime", "bool")),),
                creatable=False, group="sprite"),
    # Какие кадры листа брать: у дыма и искр в листе по 4-8 вариантов
    SimpleParam("frames", "range",
                (_v(_r("initializers", "Sequence Random", "sequence_min", "integer"),
                    _r("initializers", "Sequence Random", "sequence_max", "integer")),),
                minimum=0, maximum=63, hard_max=1000, decimals=0, group="sprite"),
    SimpleParam("draw_distance", "value",
                (_v(_r(None, "", "maximum draw distance")),),
                minimum=0, maximum=100000, hard_max=1e7, curve=CURVE_SQRT,
                decimals=0, default=100000, group="sprite", unit="u"),
)

#: Порядок разделов: в нём панель их и рисует
GROUPS = ("birth", "motion", "forces", "size", "rotation", "color", "sprite")
#: Быстрые правки по порядку кнопок
QUICK = (SCALE, DENSITY, TEMPO)
