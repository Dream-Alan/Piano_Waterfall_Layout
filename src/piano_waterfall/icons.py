"""Vector icons drawn with QPainter – no image assets or icon fonts needed."""

from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import (
    QColor,
    QIcon,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
    QPolygonF,
)

from .paths import bundled_asset

_ICON_CACHE: dict[tuple, QIcon] = {}


def _canvas(size: int = 64) -> tuple[QPixmap, QPainter]:
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    return pixmap, painter


def icon(name: str, color: str = "#e8f6ff", size: int = 64) -> QIcon:
    key = (name, color, size)
    cached = _ICON_CACHE.get(key)
    if cached is not None:
        return cached
    pixmap, painter = _canvas(size)
    scale = size / 64.0
    painter.scale(scale, scale)
    pen = QPen(QColor(color))
    pen.setWidthF(5.0)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)

    if name == "play":
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(color))
        painter.drawPolygon(QPolygonF([QPointF(25, 18), QPointF(25, 46), QPointF(48, 32)]))
    elif name == "pause":
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(color))
        painter.drawRoundedRect(QRectF(22, 18, 7, 28), 3, 3)
        painter.drawRoundedRect(QRectF(35, 18, 7, 28), 3, 3)
    elif name == "restart":
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        path = QPainterPath()
        path.arcMoveTo(QRectF(18, 18, 28, 28), 40)
        path.arcTo(QRectF(18, 18, 28, 28), 40, 290)
        painter.drawPath(path)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(color))
        painter.drawPolygon(QPolygonF([QPointF(44, 12), QPointF(50, 24), QPointF(37, 25)]))
    elif name in ("fullscreen", "fullscreen_exit"):
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        corners = [
            (18, 26, 18, 18, 26, 18),
            (38, 18, 46, 18, 46, 26),
            (46, 38, 46, 46, 38, 46),
            (26, 46, 18, 46, 18, 38),
        ]
        if name == "fullscreen_exit":
            corners = [
                (18, 18, 26, 18, 18, 26),
                (46, 18, 38, 18, 46, 26),
                (46, 46, 38, 46, 46, 38),
                (18, 46, 26, 46, 18, 38),
            ]
        for x1, y1, x2, y2, x3, y3 in corners:
            painter.drawLine(QPointF(x1, y1), QPointF(x2, y2))
            painter.drawLine(QPointF(x2, y2), QPointF(x3, y3))
    elif name == "volume":
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(color))
        painter.drawPolygon(
            QPolygonF(
                [
                    QPointF(16, 26),
                    QPointF(24, 26),
                    QPointF(33, 17),
                    QPointF(33, 47),
                    QPointF(24, 38),
                    QPointF(16, 38),
                ]
            )
        )
        painter.setPen(QPen(QColor(color), 3.2))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawArc(QRectF(33, 22, 12, 20), -70 * 16, 140 * 16)
        painter.drawArc(QRectF(35, 16, 22, 32), -70 * 16, 140 * 16)
    elif name == "folder":
        painter.setPen(QPen(QColor(color), 3.5))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        path = QPainterPath()
        path.moveTo(16, 22)
        path.lineTo(28, 22)
        path.lineTo(33, 28)
        path.lineTo(48, 28)
        path.lineTo(48, 46)
        path.lineTo(16, 46)
        path.closeSubpath()
        painter.drawPath(path)
    elif name == "ai":
        painter.setPen(QPen(QColor(color), 3.0))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRoundedRect(QRectF(18, 22, 28, 22), 6, 6)
        painter.drawLine(QPointF(26, 18), QPointF(26, 22))
        painter.drawLine(QPointF(38, 18), QPointF(38, 22))
        painter.drawLine(QPointF(26, 44), QPointF(26, 48))
        painter.drawLine(QPointF(38, 44), QPointF(38, 48))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(color))
        painter.drawEllipse(QPointF(28, 33), 2.4, 2.4)
        painter.drawEllipse(QPointF(36, 33), 2.4, 2.4)
    painter.end()
    result = QIcon(pixmap)
    _ICON_CACHE[key] = result
    return result


def app_icon(size: int = 256) -> QIcon:
    """The application logo: a miniature keyboard with falling neon notes."""

    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    s = size / 256.0
    painter.scale(s, s)

    # Rounded dark tile.
    tile = QPainterPath()
    tile.addRoundedRect(QRectF(16, 16, 224, 224), 48, 48)
    painter.setPen(Qt.PenStyle.NoPen)
    background = QLinearGradient(0, 16, 0, 240)
    background.setColorAt(0.0, QColor("#101b2e"))
    background.setColorAt(1.0, QColor("#05080f"))
    painter.setBrush(background)
    painter.drawPath(tile)
    painter.setClipPath(tile)

    # Falling notes.
    for x, top, bottom, color in (
        (78, 52, 150, QColor("#4fe3ff")),
        (122, 38, 168, QColor("#7ef0ff")),
        (166, 68, 142, QColor("#22c8ee")),
    ):
        gradient = QLinearGradient(0, top, 0, bottom)
        gradient.setColorAt(0.0, QColor(color).lighter(115))
        gradient.setColorAt(1.0, color.darker(120))
        painter.setBrush(gradient)
        painter.setPen(QPen(QColor(230, 253, 255, 150), 2))
        painter.drawRoundedRect(QRectF(x, top, 30, bottom - top), 8, 8)

    # Judgement line.
    painter.setPen(QPen(QColor("#00f0ff"), 3))
    painter.drawLine(QPointF(40, 176), QPointF(216, 176))

    # Keyboard.
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QColor("#f3f7fb"))
    for index in range(7):
        painter.drawRect(QRectF(40 + index * 22.3, 178, 22.3, 58))
    painter.setBrush(QColor("#8fd8ea"))
    painter.drawRect(QRectF(40, 210, 156, 10))
    painter.setBrush(QColor("#0c1220"))
    for index in (0, 1, 3, 4, 5):
        painter.drawRect(QRectF(40 + index * 22.3 + 14, 178, 15, 34))

    painter.end()
    return QIcon(pixmap)


def save_icon(path: str, size: int = 512) -> None:
    app_icon(size).pixmap(size, size).save(path)


def load_window_icon() -> QIcon:
    asset = bundled_asset("icon.png")
    if asset is not None:
        return QIcon(str(asset))
    return app_icon()
