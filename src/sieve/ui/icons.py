"""Small line icons drawn with QPainter, so no icon font or image plugin is needed.

Every icon is drawn on a 24x24 grid with a 2px rounded stroke and comes in two
colours: muted for the normal state and white for the selected state.
"""

from __future__ import annotations

import math
from collections.abc import Callable

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPainterPath, QPen, QPixmap

from sieve.ui import theme

Painter = Callable[[QPainter], None]
_SIZE = 24
_SCALE = 4  # draw at 96px so the icon stays crisp on high-DPI screens


def _home(p: QPainter) -> None:
    path = QPainterPath()
    path.moveTo(3, 11)
    path.lineTo(12, 3.5)
    path.lineTo(21, 11)
    p.drawPath(path)
    body = QPainterPath()
    body.moveTo(5.5, 9.5)
    body.lineTo(5.5, 20)
    body.lineTo(18.5, 20)
    body.lineTo(18.5, 9.5)
    p.drawPath(body)
    p.drawLine(QPointF(10, 20), QPointF(10, 14.5))
    p.drawLine(QPointF(10, 14.5), QPointF(14, 14.5))
    p.drawLine(QPointF(14, 14.5), QPointF(14, 20))


def _copy(p: QPainter) -> None:
    p.drawRoundedRect(QRectF(8.5, 8.5, 12, 12), 2.5, 2.5)
    path = QPainterPath()
    path.moveTo(15.5, 5.5)
    path.lineTo(15.5, 5)
    path.arcTo(QRectF(11.5, 3.5, 4, 4), 0, 90)
    path.lineTo(5.5, 3.5)
    path.arcTo(QRectF(3.5, 3.5, 4, 4), 90, 90)
    path.lineTo(3.5, 13.5)
    path.arcTo(QRectF(3.5, 11.5, 4, 4), 180, 90)
    path.lineTo(5.5, 15.5)
    p.drawPath(path)


def _filter(p: QPainter) -> None:
    path = QPainterPath()
    path.moveTo(3.5, 4.5)
    path.lineTo(20.5, 4.5)
    path.lineTo(14, 12.5)
    path.lineTo(14, 19)
    path.lineTo(10, 21)
    path.lineTo(10, 12.5)
    path.closeSubpath()
    p.drawPath(path)


def _settings(p: QPainter) -> None:
    center = QPointF(12, 12)
    p.drawEllipse(center, 3, 3)
    p.drawEllipse(center, 7, 7)
    for i in range(8):
        a = math.radians(i * 45)
        p.drawLine(
            QPointF(12 + 7 * math.cos(a), 12 + 7 * math.sin(a)),
            QPointF(12 + 9.5 * math.cos(a), 12 + 9.5 * math.sin(a)),
        )


def _info(p: QPainter) -> None:
    p.drawEllipse(QPointF(12, 12), 9, 9)
    p.drawLine(QPointF(12, 11), QPointF(12, 16.5))
    p.drawPoint(QPointF(12, 7.6))


def _menu(p: QPainter) -> None:
    for y in (6.5, 12, 17.5):
        p.drawLine(QPointF(4, y), QPointF(20, y))


def _collapse(p: QPainter) -> None:
    p.drawRoundedRect(QRectF(3.5, 4.5, 17, 15), 2.5, 2.5)
    p.drawLine(QPointF(9, 4.5), QPointF(9, 19.5))
    path = QPainterPath()
    path.moveTo(15.5, 9)
    path.lineTo(12.5, 12)
    path.lineTo(15.5, 15)
    p.drawPath(path)


def _eraser(p: QPainter) -> None:
    body = QPainterPath()
    body.moveTo(13.5, 4.5)
    body.lineTo(20, 11)
    body.lineTo(11.5, 19.5)
    body.lineTo(7.5, 19.5)
    body.lineTo(4, 16)
    body.closeSubpath()
    p.drawPath(body)
    p.drawLine(QPointF(8.5, 9.5), QPointF(15, 16))
    p.drawLine(QPointF(11.5, 19.5), QPointF(20, 19.5))


def _link(p: QPainter) -> None:
    p.save()
    p.translate(12, 12)
    p.rotate(-45)
    p.drawRoundedRect(QRectF(-9.5, -3.5, 10, 7), 3.5, 3.5)
    p.drawRoundedRect(QRectF(-0.5, -3.5, 10, 7), 3.5, 3.5)
    p.restore()


def _tool(p: QPainter) -> None:
    for x, y in ((4, 4), (13, 4), (4, 13), (13, 13)):
        p.drawRoundedRect(QRectF(x, y, 7, 7), 1.5, 1.5)


ICONS: dict[str, Painter] = {
    "home": _home,
    "copy": _copy,
    "filter": _filter,
    "settings": _settings,
    "info": _info,
    "menu": _menu,
    "collapse": _collapse,
    "eraser": _eraser,
    "link": _link,
    "tool": _tool,
}


def _pixmap(draw: Painter, color: str) -> QPixmap:
    pixmap = QPixmap(_SIZE * _SCALE, _SIZE * _SCALE)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.scale(_SCALE, _SCALE)
    pen = QPen(QColor(color), 1.9)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    painter.setPen(pen)
    painter.setBrush(Qt.BrushStyle.NoBrush)
    draw(painter)
    painter.end()
    return pixmap


def icon(name: str) -> QIcon:
    draw = ICONS.get(name, _tool)
    result = QIcon()
    result.addPixmap(_pixmap(draw, theme.TEXT_MUTED), QIcon.Mode.Normal)
    result.addPixmap(_pixmap(draw, theme.TEXT), QIcon.Mode.Active)
    result.addPixmap(_pixmap(draw, "#ffffff"), QIcon.Mode.Selected)
    return result
