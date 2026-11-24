"""
Правки VMT предмета - часть его работы, как текстуры и карты

Раньше правка лежала в общей папке по одному имени материала и подставлялась
при любом открытии предмета: стоковый обрез из каталога приходил с чужим
эффектом крита, «Забыть правки» и удаление работы её не трогали, и она молча
уходила в каждую сборку. Теперь она живёт в состоянии предмета: пишется в
работу автосохранением, возвращается «Вернуть правки», отменяется Ctrl+Z

Ключ - тот же, что был именем файла: материал (`c_scattergun`) или ключ
материала мода (EditedVMTService.mod_key). Рядом - игровой оригинал, снятый
при первой правке: по нему «Вернуть игровой» возвращает игру, а не прошлую
правку
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Optional


@dataclass
class VmtEdits:
    #: {ключ: текст правки}
    texts: Dict[str, str] = field(default_factory=dict)
    #: {ключ: игровой оригинал на момент первой правки}
    origs: Dict[str, str] = field(default_factory=dict)

    def as_edits(self) -> Dict[str, object]:
        """Для user_edits: оригиналы - только у правленых, остальные лишние"""
        return {'vmt_edits': dict(self.texts),
                'vmt_origs': {k: v for k, v in self.origs.items() if k in self.texts}}

    def apply(self, edits: Optional[Dict[str, object]]) -> None:
        """Из работы. Чего нет - правок нет: VMT работы целиком её"""
        edits = edits or {}
        self.texts = {str(k): str(v) for k, v in (edits.get('vmt_edits') or {}).items() if v}
        self.origs = {str(k): str(v) for k, v in (edits.get('vmt_origs') or {}).items()
                      if v and k in self.texts}

    def clear(self) -> None:
        self.texts = {}
        self.origs = {}

    @staticmethod
    def without(edits: Dict[str, object]) -> Dict[str, object]:
        """Правки без VMT - для снимка стиля шапки. Файл материала у стилей
        обычно общий, поэтому правка VMT - на всю шапку, а не на стиль"""
        return {k: v for k, v in edits.items() if k not in ('vmt_edits', 'vmt_origs')}

    def merged(self, older: 'VmtEdits') -> 'VmtEdits':
        """Эти правки поверх более старых (снимок стиля из прошлой версии)"""
        return VmtEdits({**older.texts, **self.texts}, {**older.origs, **self.origs})

    def copy(self) -> 'VmtEdits':
        """Снимок для сборки: она идёт фоном, а человек тем временем может
        открыть другой предмет"""
        return VmtEdits(dict(self.texts), dict(self.origs))
