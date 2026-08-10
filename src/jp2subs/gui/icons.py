"""Vector icons drawn at runtime.

Shipping no image files keeps the PyInstaller bundle simple and lets every icon
pick up the active theme colour. All shapes are authored on a 24x24 grid.
"""
from __future__ import annotations

from PySide6 import QtCore, QtGui

from . import theme

_GRID = 24.0

# Each icon is a list of primitives: ("line", x1, y1, x2, y2),
# ("poly", x1, y1, x2, y2, ...), ("rect", x, y, w, h, radius),
# ("circle", cx, cy, r), ("dot", cx, cy, r).
_SHAPES: dict[str, list[tuple]] = {
    "waveform": [
        ("line", 3, 12, 3, 12),
        ("line", 6, 8, 6, 16),
        ("line", 10, 4, 10, 20),
        ("line", 14, 7, 14, 17),
        ("line", 18, 10, 18, 14),
        ("line", 21, 11, 21, 13),
    ],
    "film": [
        ("rect", 3, 5, 18, 14, 2),
        ("line", 8, 5, 8, 19),
        ("line", 16, 5, 16, 19),
        ("line", 3, 12, 21, 12),
    ],
    "download": [
        ("line", 12, 3, 12, 15),
        ("poly", 7, 10, 12, 15, 17, 10),
        ("poly", 4, 17, 4, 20, 20, 20, 20, 17),
    ],
    "sliders": [
        ("line", 4, 7, 20, 7),
        ("line", 4, 17, 20, 17),
        ("dot", 9, 7, 2.6),
        ("dot", 16, 17, 2.6),
    ],
    "info": [
        ("circle", 12, 12, 9),
        ("line", 12, 11, 12, 16),
        ("dot", 12, 8, 1.1),
    ],
    "check": [
        ("poly", 5, 13, 10, 18, 19, 6),
    ],
    "folder": [
        ("poly", 3, 19, 3, 6, 10, 6, 12, 9, 21, 9, 21, 19, 3, 19),
    ],
    "play": [
        ("poly", 8, 5, 19, 12, 8, 19, 8, 5),
    ],
    "stop": [
        ("rect", 7, 7, 10, 10, 2),
    ],
    "trash": [
        ("line", 4, 7, 20, 7),
        ("poly", 6, 7, 7, 20, 17, 20, 18, 7),
        ("poly", 9, 7, 9, 4, 15, 4, 15, 7),
    ],
    "refresh": [
        ("arc", 12, 12, 8, 40, 280),
        ("poly", 17, 3, 19, 7, 15, 8),
    ],
    "plus": [
        ("line", 12, 5, 12, 19),
        ("line", 5, 12, 19, 12),
    ],
    "alert": [
        ("poly", 12, 4, 21, 20, 3, 20, 12, 4),
        ("line", 12, 10, 12, 14),
        ("dot", 12, 17, 1.0),
    ],
    "spark": [
        ("poly", 12, 3, 14, 10, 21, 12, 14, 14, 12, 21, 10, 14, 3, 12, 10, 10, 12, 3),
    ],
    "cpu": [
        ("rect", 6, 6, 12, 12, 2),
        ("line", 10, 3, 10, 6),
        ("line", 14, 3, 14, 6),
        ("line", 10, 18, 10, 21),
        ("line", 14, 18, 14, 21),
        ("line", 3, 10, 6, 10),
        ("line", 3, 14, 6, 14),
        ("line", 18, 10, 21, 10),
        ("line", 18, 14, 21, 14),
    ],
    "external": [
        ("poly", 14, 4, 20, 4, 20, 10),
        ("line", 20, 4, 12, 12),
        ("poly", 17, 14, 17, 20, 4, 20, 4, 7, 10, 7),
    ],
}


def _pen_color(color: str | QtGui.QColor | None) -> QtGui.QColor:
    if color is None:
        return QtGui.QColor(theme.active_palette().text)
    if isinstance(color, QtGui.QColor):
        return color
    return QtGui.QColor(color)


def pixmap(name: str, size: int = 20, color: str | QtGui.QColor | None = None, width: float = 1.9) -> QtGui.QPixmap:
    """Render one icon at ``size`` device-independent pixels."""

    ratio = QtGui.QGuiApplication.primaryScreen().devicePixelRatio() if QtGui.QGuiApplication.instance() else 1.0
    canvas = QtGui.QPixmap(int(size * ratio), int(size * ratio))
    canvas.setDevicePixelRatio(ratio)
    canvas.fill(QtCore.Qt.transparent)

    shapes = _SHAPES.get(name)
    if not shapes:
        return canvas

    painter = QtGui.QPainter(canvas)
    painter.setRenderHint(QtGui.QPainter.Antialiasing)
    scale = size / _GRID
    painter.scale(scale * ratio, scale * ratio)

    color_value = _pen_color(color)
    pen = QtGui.QPen(color_value)
    pen.setWidthF(width)
    pen.setCapStyle(QtCore.Qt.RoundCap)
    pen.setJoinStyle(QtCore.Qt.RoundJoin)
    painter.setPen(pen)
    painter.setBrush(QtCore.Qt.NoBrush)

    for shape in shapes:
        kind = shape[0]
        if kind == "line":
            painter.drawLine(QtCore.QPointF(shape[1], shape[2]), QtCore.QPointF(shape[3], shape[4]))
        elif kind == "poly":
            points = [QtCore.QPointF(shape[i], shape[i + 1]) for i in range(1, len(shape) - 1, 2)]
            painter.drawPolyline(points)
        elif kind == "rect":
            painter.drawRoundedRect(QtCore.QRectF(shape[1], shape[2], shape[3], shape[4]), shape[5], shape[5])
        elif kind == "circle":
            painter.drawEllipse(QtCore.QPointF(shape[1], shape[2]), shape[3], shape[3])
        elif kind == "dot":
            painter.setBrush(color_value)
            painter.drawEllipse(QtCore.QPointF(shape[1], shape[2]), shape[3], shape[3])
            painter.setBrush(QtCore.Qt.NoBrush)
        elif kind == "arc":
            cx, cy, radius, start, span = shape[1:]
            rect = QtCore.QRectF(cx - radius, cy - radius, radius * 2, radius * 2)
            painter.drawArc(rect, int(start * 16), int(span * 16))

    painter.end()
    return canvas


def icon(name: str, size: int = 20, color: str | QtGui.QColor | None = None) -> QtGui.QIcon:
    return QtGui.QIcon(pixmap(name, size=size, color=color))


def app_logo(size: int = 40) -> QtGui.QPixmap:
    """Rounded accent tile with a waveform, used as the app mark and window icon."""

    ratio = QtGui.QGuiApplication.primaryScreen().devicePixelRatio() if QtGui.QGuiApplication.instance() else 1.0
    canvas = QtGui.QPixmap(int(size * ratio), int(size * ratio))
    canvas.setDevicePixelRatio(ratio)
    canvas.fill(QtCore.Qt.transparent)

    colors = theme.active_palette()
    painter = QtGui.QPainter(canvas)
    painter.setRenderHint(QtGui.QPainter.Antialiasing)
    painter.scale(ratio, ratio)

    gradient = QtGui.QLinearGradient(0, 0, size, size)
    gradient.setColorAt(0.0, QtGui.QColor(colors.accent_hover))
    gradient.setColorAt(1.0, QtGui.QColor(colors.accent_pressed))
    painter.setBrush(QtGui.QBrush(gradient))
    painter.setPen(QtCore.Qt.NoPen)
    painter.drawRoundedRect(QtCore.QRectF(0, 0, size, size), size * 0.28, size * 0.28)

    pen = QtGui.QPen(QtGui.QColor("#ffffff"))
    pen.setWidthF(max(size * 0.07, 1.4))
    pen.setCapStyle(QtCore.Qt.RoundCap)
    painter.setPen(pen)

    unit = size / 24.0
    bars = ((7, 9, 15), (11, 6, 18), (15, 8, 16), (19, 11, 13))
    for x, top, bottom in bars:
        painter.drawLine(
            QtCore.QPointF(x * unit, top * unit),
            QtCore.QPointF(x * unit, bottom * unit),
        )

    painter.end()
    return canvas
