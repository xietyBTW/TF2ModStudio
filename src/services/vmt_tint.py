"""
Командная окраска материала: $blendtintbybasealpha в понятном виде

Две трети шапок TF2 (1353 модели из 1978 в стоке) не хранят цвет команды в
текстуре. Вместо этого альфа-канал `$basetexture` - это МАСКА окраски, а сам
цвет лежит в VMT (`$colortint_base`/`$color2`) и подмешивается шейдером:

    tinted = base_rgb * color
    tinted = lerp(tinted, color, $blendtintcoloroverbase)
    out    = lerp(base_rgb, tinted, base_alpha)

Отсюда два эффекта, которые видит пользователь, если этого не учитывать:

* окрашиваемые участки в текстуре почти чёрные (их цвет всё равно заменит
  краска), и превью показывает шапку с чёрными пятнами;
* RED и BLU у таких шапок ссылаются на ОДНУ текстуру и отличаются только
  цветом в VMT - переключатель команд показывает две одинаковые картинки

Без обращений к VPK: на вход текст VMT и PNG-файл
"""

import json
import os
import re
from dataclasses import dataclass
from typing import Optional, Tuple

from src.services import vmt_parse
from src.services.vtf_preview_service import PREVIEW_PNG_COMPRESS
from src.shared.logging_config import get_logger

logger = get_logger(__name__)

#: Разбор цвета VMT - общий (фигурные скобки 0-255, квадратные - доли)
parse_color = vmt_parse.parse_color

#: Прокси, который пишет в `$color2`: написанное в VMT значение при нём не действует
_COLOR2_WRITTEN = re.compile(r'resultvar"?\s+"?\$color2\b', re.IGNORECASE)


@dataclass(frozen=True)
class TintSpec:
    """Как красить текстуру: цвет и насколько он перекрывает базовый"""
    color: Tuple[int, int, int]
    over_base: float = 0.0
    #: Цвет множит всю картинку, а альфа остаётся как была: без
    #: `$blendtintbybasealpha` цвет VMT ложится не по маске
    whole: bool = False
    #: Цвет вписан в сам материал: прокси ItemTintColor нет, и банка краски
    #: его в игре не меняет
    fixed: bool = False

    @property
    def is_neutral(self) -> bool:
        """Белая краска поверх нуля ничего не меняет - красить нечего"""
        return self.color == (255, 255, 255) and self.over_base <= 0.0


def parse_tint(vmt_text: str) -> Optional[TintSpec]:
    """
    Краска материала либо None, если материал так не красится

    None означает «текстуру трогать нельзя»: у обычного материала альфа -
    это прозрачность, а не маска краски, и заливать её нельзя
    """
    if not vmt_text:
        return None
    vmt = vmt_parse.parse(vmt_text)
    if not vmt.flag("blendtintbybasealpha"):
        return None
    # Прозрачность и маска краски в одном материале несовместимы: раз VMT
    # просит прозрачность, альфу считаем прозрачностью и не трогаем
    if vmt.flag("translucent") or vmt.flag("alphatest"):
        return None
    return _masked(vmt)


def _masked(vmt) -> TintSpec:
    """Краска по альфе текстуры (`$blendtintbybasealpha`)"""
    color = vmt.color("colortint_base") or vmt.color("color2")
    if color is None:
        color = (255, 255, 255)     # краски нет, но альфа-маска всё равно есть
    over_base = vmt.number("blendtintcoloroverbase", 0.0) or 0.0
    return TintSpec(color, max(0.0, min(1.0, over_base)))


def preview_tint(vmt_text: str) -> Optional[TintSpec]:
    """
    Краска материала для превью: всё, чем цвет VMT меняет картинку в игре

    Шире `parse_tint`, по которому сборка решает про маску краски. Шейдер
    моделей (skin_ps20b.fxc в SDK) красит двумя способами:

    * с `$blendtintbybasealpha` - по альфе текстуры. Прозрачность при этом
      берётся не из неё, так что `$translucent` маске не мешает: у «Рыцаря
      Туфорта» так светится забрало, красным или синим по команде;
    * без него - множит цветом всю картинку. У Doublecross-Comm огонёк
      гарнитуры отличается у команд только этим цветом

    Написанный `$color2` действует, только пока его не переписывают прокси.
    С ItemTintColor в него попадает `$colortint_base` (и тогда цвет меняет
    банка краски). Остальные шаблоны кладут туда YellowLevel, обычно белый:
    у Sightseer в VMT стоит `$color2 {0 0 0}`, а шапка не чёрная
    """
    if not vmt_text:
        return None
    vmt = vmt_parse.parse(vmt_text)
    if vmt.flag("blendtintbybasealpha"):
        return _masked(vmt)
    if "itemtintcolor" in vmt_text.lower():
        color, fixed = vmt.color("colortint_base") or vmt.color("color2"), False
    elif _COLOR2_WRITTEN.search(vmt_text):
        return None
    else:
        color, fixed = vmt.color("color2"), True
    if color is None or color == (255, 255, 255):
        return None
    return TintSpec(color, whole=True, fixed=fixed)


def apply_to_png(png_path: str, spec: Optional[TintSpec]) -> bool:
    """
    Впечатывает краску в PNG на месте: то, что игрок увидит в игре

    Альфа после этого - сплошная непрозрачность: в исходной текстуре она
    была маской краски, и оставлять её значит показывать шапку дырявой.
    Сама маска при этом не пропадает: исходник остаётся рядом (`raw_of`),
    а краска - в соседнем JSON, чтобы превью могло перекрасить шапку любой
    банкой из игры (`painted`)

    Returns:
        True, если файл изменён
    """
    if spec is None or not png_path:
        return False
    try:
        from PIL import Image
    except ImportError:
        return False
    try:
        with Image.open(png_path) as img:
            src = img.convert("RGBA")
        src.save(raw_of(png_path), compress_level=PREVIEW_PNG_COMPRESS)
        if not spec.fixed:
            with open(png_path + ".paint.json", "w", encoding="utf-8") as f:
                json.dump({"color": list(spec.color), "over": spec.over_base,
                           "whole": spec.whole}, f)
        _tinted(src, spec).save(png_path, compress_level=PREVIEW_PNG_COMPRESS)
        return True
    except Exception as exc:
        logger.warning(f"[tint] окраска {png_path} не удалась: {exc}")
        return False


def _tinted(src, spec: TintSpec):
    """Формула шейдера на картинке RGBA: альфа - маска, на выходе непрозрачно.
    У краски на всю картинку (`whole`) маски нет, и альфа остаётся своей"""
    from PIL import Image, ImageChops

    r, g, b, alpha = src.split()
    base = Image.merge("RGB", (r, g, b))
    if spec.whole:
        out = Image.merge("RGB", [
            ImageChops.multiply(ch, Image.new("L", src.size, level))
            for ch, level in zip((r, g, b), spec.color)])
        out.putalpha(alpha)
        return out
    if spec.is_neutral:
        tinted = base
    else:
        multiplied = Image.merge("RGB", [
            ImageChops.multiply(ch, Image.new("L", src.size, level))
            for ch, level in zip((r, g, b), spec.color)])
        flat = Image.new("RGB", src.size, spec.color)
        tinted = (multiplied if spec.over_base <= 0 else
                  Image.blend(multiplied, flat, spec.over_base))
    out = Image.composite(tinted, base, alpha)
    out.putalpha(Image.new("L", src.size, 255))
    return out


def lacks_alpha(image_path: str) -> bool:
    """
    Нет ли у картинки своей альфы: канала нет вовсе или он сплошь белый

    Для материала с `$blendtintbybasealpha` это значит «красить ВСЁ»: игра
    кладёт цвет VMT туда, где альфа белая, а картинка без альфы становится
    текстурой с белой альфой целиком. Так Cow Mangler с чужой текстурой
    выходил в игре красным от ствола до приклада
    """
    try:
        from PIL import Image
        with Image.open(image_path) as img:
            if "A" not in img.getbands() and "transparency" not in img.info:
                return True
            low, _ = img.convert("RGBA").getchannel("A").getextrema()
            return low >= 250
    except Exception as exc:
        logger.warning(f"[tint] не прочитать альфу {image_path}: {exc}")
        return False


def with_mask(image_path: str, out_path: str,
              mask_png: Optional[str] = None) -> bool:
    """
    Копия картинки с альфой-маской краски: из `mask_png` (альфа игрового
    оригинала, растянутая под размер) или пустой - тогда игра не красит ничего

    Развёртка у модели одна на всех, поэтому маска оригинала ложится на те же
    места и своей текстуры
    """
    try:
        from PIL import Image
        with Image.open(image_path) as img:
            rgb = img.convert("RGB")
        if mask_png:
            with Image.open(mask_png) as m:
                alpha = m.convert("RGBA").getchannel("A").resize(rgb.size, Image.LANCZOS)
        else:
            alpha = Image.new("L", rgb.size, 0)
        rgb.putalpha(alpha)
        rgb.save(out_path)
        return True
    except Exception as exc:
        logger.warning(f"[tint] маска для {image_path} не наложена: {exc}")
        return False


#: Названия цвета краски для предупреждения: (верхняя граница тона, ru, en)
_HUES = ((15, "красный", "red"), (40, "оранжевый", "orange"),
         (70, "жёлтый", "yellow"), (165, "зелёный", "green"),
         (200, "голубой", "light blue"), (255, "синий", "blue"),
         (290, "фиолетовый", "purple"), (345, "розовый", "pink"),
         (360, "красный", "red"))


def color_name(rgb: Tuple[int, int, int], lang: str = "en") -> str:
    """Словом, какой это цвет: «красный». Точный цвет человеку ничего не скажет"""
    import colorsys
    h, s, v = colorsys.rgb_to_hsv(*(c / 255 for c in rgb))
    if s < 0.2 or v < 0.15:
        return "серый" if lang == "ru" else "gray"
    deg = h * 360
    for top, ru, en in _HUES:
        if deg < top:
            return ru if lang == "ru" else en
    return "красный" if lang == "ru" else "red"


def raw_of(png_path: str) -> str:
    """Где лежит исходник с маской у окрашенной картинки"""
    return png_path + ".raw.png"


def paintable(png_path: Optional[str]) -> Optional[TintSpec]:
    """Краска игры у картинки превью, если её красили через `apply_to_png`"""
    if not png_path:
        return None
    try:
        with open(png_path + ".paint.json", encoding="utf-8") as f:
            data = json.load(f)
        return TintSpec(tuple(int(c) for c in data["color"]), float(data.get("over", 0.0)),
                        whole=bool(data.get("whole", False)))
    except (OSError, ValueError, KeyError, TypeError):
        return None


def painted(raw_png: str, spec: TintSpec, out_dir: str) -> Optional[str]:
    """
    Картинка, покрашенная краской `spec` по маске исходника, - для превью

    Имя файла несёт цвет и время исходника: другая краска или новая
    текстура - новый файл, и браузер не покажет старый из кэша
    """
    try:
        from PIL import Image

        stamp = int(os.stat(raw_png).st_mtime)
        name = (f"{os.path.splitext(os.path.basename(raw_png))[0]}"
                f"_{spec.color[0]:02x}{spec.color[1]:02x}{spec.color[2]:02x}"
                f"_{int(spec.over_base * 100)}_{stamp}.png")
        out = os.path.join(out_dir, name)
        if os.path.isfile(out):
            return out
        with Image.open(raw_png) as img:
            src = img.convert("RGBA")
        _tinted(src, spec).save(out, compress_level=PREVIEW_PNG_COMPRESS)
        return out
    except Exception as exc:
        logger.warning(f"[tint] покраска {raw_png} не удалась: {exc}")
        return None
