"""Минималистичные линейные иконки (встроенные SVG, без внешних файлов) — единый стиль для меню и кнопок."""
from __future__ import annotations
from functools import lru_cache

from PySide6.QtCore import QByteArray, QRectF, Qt
from PySide6.QtGui import QIcon, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer

# 24×24, контур; цвет подставляется в {c}
_PATHS = {
    "home": '<path d="M3 10.5 12 3l9 7.5"/><path d="M5 9.5V21h14V9.5"/><path d="M10 21v-6h4v6"/>',
    "paw": '<circle cx="7" cy="9" r="2"/><circle cx="12" cy="6" r="2"/><circle cx="17" cy="9" r="2"/>'
           '<path d="M8 17.5c0-2.5 1.8-5 4-5s4 2.5 4 5c0 1.7-1.6 2.5-4 2.5s-4-.8-4-2.5z"/>',
    "calendar": '<rect x="3.5" y="5" width="17" height="15" rx="2"/><path d="M3.5 10h17M8 3v4M16 3v4"/>',
    "check": '<rect x="3.5" y="3.5" width="17" height="17" rx="3"/><path d="m8 12 3 3 5-6"/>',
    "box": '<path d="M3.5 7.5 12 3l8.5 4.5v9L12 21l-8.5-4.5z"/><path d="M3.5 7.5 12 12l8.5-4.5M12 12v9"/>',
    "users": '<circle cx="9" cy="8" r="3.5"/><path d="M2.5 20c.5-3.5 3.2-5.5 6.5-5.5s6 2 6.5 5.5"/>'
             '<path d="M16 4.8a3.3 3.3 0 0 1 0 6.4M18 14.8c2 .7 3.2 2.5 3.5 5.2"/>',
    "doctor": '<circle cx="12" cy="7" r="4"/><path d="M4.5 21c.6-4.3 3.6-7 7.5-7s6.9 2.7 7.5 7"/>'
              '<path d="M12 15.5v3M10.5 17h3"/>',
    "tag": '<path d="M3.5 12.5V4.5a1 1 0 0 1 1-1h8l8 8-9 9z"/><circle cx="8" cy="8" r="1.5"/>',
    "chart": '<path d="M4 20V4M4 20h16"/><path d="M8 16v-4M12 16V8M16 16v-6"/>',
    "bell": '<path d="M6 16V11a6 6 0 0 1 12 0v5l1.5 2h-15z"/><path d="M10 20.5a2 2 0 0 0 4 0"/>',
    "plus": '<path d="M12 5v14M5 12h14"/>',
    "refresh": '<path d="M20 11a8 8 0 0 0-14.5-4.5L4 8"/><path d="M4 4v4h4"/>'
               '<path d="M4 13a8 8 0 0 0 14.5 4.5L20 16"/><path d="M20 20v-4h-4"/>',
    "card": '<rect x="3" y="5.5" width="18" height="13" rx="2"/><path d="M3 10h18M7 15h3"/>',
    "print": '<path d="M7 8V3.5h10V8"/><rect x="3.5" y="8" width="17" height="8" rx="2"/><path d="M7 13h10v7.5H7z"/>',
    "close": '<path d="m6 12 4 4 8-8"/>',
}


@lru_cache(maxsize=None)
def icon(name: str, color: str = "#4b5563", size: int = 48) -> QIcon:
    body = _PATHS.get(name, "")
    svg = (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="{color}" '
           f'stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round">{body}</svg>')
    renderer = QSvgRenderer(QByteArray(svg.encode()))
    pm = QPixmap(size, size)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    renderer.render(p, QRectF(0, 0, size, size))
    p.end()
    ic = QIcon(pm)
    return ic


def nav_icon(name: str) -> QIcon:
    """Иконка раздела: серая в обычном состоянии, цвета акцента — у выбранного пункта."""
    ic = QIcon()
    ic.addPixmap(icon(name, "#6b7280").pixmap(48), QIcon.Mode.Normal)
    ic.addPixmap(icon(name, "#0f766e").pixmap(48), QIcon.Mode.Selected)
    return ic
