"""The animated piano waterfall.

Everything is painted with :class:`QPainter`, so the same widget powers the
desktop app and the head-less screenshot renderer used for the README.
"""

from __future__ import annotations

import bisect
import math
from dataclasses import dataclass

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import (
    QColor,
    QFont,
    QFontMetrics,
    QLinearGradient,
    QPainter,
    QPen,
    QRadialGradient,
)
from PySide6.QtWidgets import QWidget

from .layout import KeyboardLayout, fit_keyboard_range
from .midi_io import Song, note_name
from .theme import Theme, get_theme


@dataclass(slots=True)
class Particle:
    x: float
    y: float
    vx: float
    vy: float
    life: float
    max_life: float
    color: QColor
    radius: float


class WaterfallWidget(QWidget):
    """Draws falling notes over a keyboard.

    The widget is passive: call :meth:`set_time` from a timer (the app feeds
    it the playback clock).  That keeps seeking, pausing and playback-rate
    changes perfectly in sync.
    """

    note_pressed = Signal(int)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setMinimumSize(640, 360)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent, True)

        self._song: Song | None = None
        self._layout: KeyboardLayout | None = None
        self._theme: Theme = get_theme("neon")
        self._theme_version = 0
        self._layout_width = 0

        self._time = 0.0
        self._prev_time = 0.0
        self._fall_speed = 430.0
        self._piano_ratio = 0.165
        self._rainbow = False

        self._starts: list[float] = []
        self._ends: list[float] = []
        self._max_duration = 0.0

        self._pressed: set[int] = set()
        self._particles: list[Particle] = []

        self._overlay_title = "拖入 MIDI 或音频文件"
        self._overlay_subtitle = "支持 .mid .midi .wav .mp3 .flac .ogg"
        self._overlay_progress: float | None = None
        self._overlay_visible = True
        self._title_text = ""

        self._brush_cache: dict[tuple[str, str], QLinearGradient] = {}
        self._font_cache: dict[tuple[int, bool], QFont] = {}

    # ------------------------------------------------------------------ API
    def set_song(self, song: Song | None, *, title: str = "") -> None:
        self._song = song
        self._title_text = title
        self._pressed.clear()
        self._particles.clear()
        self._time = 0.0
        self._prev_time = 0.0
        if song is None:
            self._starts, self._ends, self._max_duration = [], [], 0.0
        else:
            low, high = song.pitch_range
            self._key_min, self._key_max = fit_keyboard_range(low, high)
            padded = [n for n in song.notes]
            self._starts = [n.start for n in padded]
            self._ends = [n.end for n in padded]
            self._max_duration = max((n.duration for n in padded), default=0.0)
        self._layout = None
        self._layout_width = 0
        self._overlay_visible = song is None
        self.update()

    def set_theme(self, theme: Theme | str) -> None:
        self._theme = get_theme(theme) if isinstance(theme, str) else theme
        self._theme_version += 1
        self._brush_cache.clear()
        self._font_cache.clear()
        self.update()

    @property
    def theme(self) -> Theme:
        return self._theme

    def set_fall_speed(self, pixels_per_second: float) -> None:
        self._fall_speed = max(120.0, min(float(pixels_per_second), 1400.0))
        self.update()

    @property
    def fall_speed(self) -> float:
        return self._fall_speed

    def set_rainbow(self, enabled: bool) -> None:
        self._rainbow = bool(enabled)
        self._brush_cache.clear()
        self.update()

    def set_time(self, seconds: float) -> None:
        seconds = max(0.0, float(seconds))
        jump = abs(seconds - self._time)
        previous = self._time
        self._prev_time = previous
        self._time = seconds
        if jump > 0.35 or seconds < previous:
            self._particles.clear()
        else:
            self._spawn_hits(previous, seconds)
            self._advance_particles(seconds - previous)
        self.update()

    @property
    def time(self) -> float:
        return self._time

    def show_overlay(
        self,
        title: str,
        subtitle: str = "",
        progress: float | None = None,
    ) -> None:
        self._overlay_title = title
        self._overlay_subtitle = subtitle
        self._overlay_progress = progress
        self._overlay_visible = True
        self.update()

    def hide_overlay(self) -> None:
        self._overlay_visible = False
        self._overlay_progress = None
        self.update()

    # ------------------------------------------------------------- painting
    def paintEvent(self, event) -> None:  # noqa: N802 (Qt naming)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)

        width = float(self.width())
        height = float(self.height())
        piano_height = self._piano_height(height)
        line_y = height - piano_height
        layout = self._ensure_layout(width)

        self._paint_background(painter, width, height, line_y)
        if self._song is not None and layout is not None:
            self._paint_lanes(painter, width, line_y, layout)
            self._paint_notes(painter, width, line_y, layout)
            self._paint_particles(painter, line_y)
            self._paint_hit_line(painter, width, line_y)
            self._paint_keyboard(painter, width, height, line_y, piano_height, layout)
        else:
            self._paint_empty_stage(painter, width, height, line_y)

        if self._overlay_visible:
            self._paint_overlay(painter, width, height)
        painter.end()

    def _piano_height(self, height: float) -> float:
        return max(90.0, min(height * self._piano_ratio, height * 0.30))

    def _ensure_layout(self, width: float) -> KeyboardLayout | None:
        if self._song is None:
            return None
        if self._layout is None or abs(self._layout_width - width) > 0.5:
            low, high = getattr(self, "_key_min", 48), getattr(self, "_key_max", 84)
            self._layout = KeyboardLayout(low, high, width)
            self._layout_width = width
            self._brush_cache.clear()
        return self._layout

    def _color(self, value: str, alpha: int = 255) -> QColor:
        color = QColor(value)
        color.setAlpha(max(0, min(alpha, 255)))
        return color

    def _gradient_brush(self, top: str, bottom: str) -> QLinearGradient:
        key = (top, bottom)
        gradient = self._brush_cache.get(key)
        if gradient is None:
            gradient = QLinearGradient(0.0, 0.0, 0.0, 1.0)
            gradient.setCoordinateMode(QLinearGradient.CoordinateMode.ObjectBoundingMode)
            gradient.setColorAt(0.0, QColor(top))
            gradient.setColorAt(1.0, QColor(bottom))
            self._brush_cache[key] = gradient
        return gradient

    def _font(self, pixels: int, bold: bool = False) -> QFont:
        key = (pixels, bold)
        font = self._font_cache.get(key)
        if font is None:
            font = QFont()
            font.setFamilies(
                [
                    "Segoe UI Variable",
                    "Segoe UI",
                    "Microsoft YaHei UI",
                    "PingFang SC",
                    "Noto Sans CJK SC",
                ]
            )
            font.setPixelSize(pixels)
            font.setBold(bold)
            self._font_cache[key] = font
        return font

    # ... background pieces ------------------------------------------------
    def _paint_background(
        self, painter: QPainter, width: float, height: float, line_y: float
    ) -> None:
        theme = self._theme
        gradient = QLinearGradient(0.0, 0.0, 0.0, height)
        gradient.setColorAt(0.0, QColor(theme.bg_top))
        gradient.setColorAt(1.0, QColor(theme.bg_bottom))
        painter.fillRect(QRectF(0.0, 0.0, width, height), gradient)

        glow = QRadialGradient(QPointF(width / 2.0, line_y), max(width, height) * 0.62)
        color = QColor(theme.glow)
        color.setAlpha(160)
        glow.setColorAt(0.0, color)
        color2 = QColor(theme.glow)
        color2.setAlpha(0)
        glow.setColorAt(1.0, color2)
        painter.fillRect(QRectF(0.0, 0.0, width, line_y), glow)

        # Vignette on the sides for depth.
        side = QLinearGradient(0.0, 0.0, width, 0.0)
        side.setColorAt(0.0, QColor(0, 0, 0, 90))
        side.setColorAt(0.18, QColor(0, 0, 0, 0))
        side.setColorAt(0.82, QColor(0, 0, 0, 0))
        side.setColorAt(1.0, QColor(0, 0, 0, 90))
        painter.fillRect(QRectF(0.0, 0.0, width, line_y), side)

    def _paint_lanes(
        self, painter: QPainter, width: float, line_y: float, layout: KeyboardLayout
    ) -> None:
        painter.save()
        pen = QPen(QColor(255, 255, 255, 10))
        pen.setWidthF(1.0)
        painter.setPen(pen)
        for key in layout.white_keys():
            x = key.x + key.width
            painter.drawLine(QPointF(x, 0.0), QPointF(x, line_y))
        painter.restore()

    # ... notes ------------------------------------------------------------
    def _note_colors(self, pitch: int) -> tuple[str, str, str]:
        theme = self._theme
        if not self._rainbow:
            return theme.note_top, theme.note_bottom, theme.note_glow
        hue = int((pitch % 12) / 12.0 * 360)
        top = QColor.fromHsv(hue, 110, 255).name()
        bottom = QColor.fromHsv(hue, 235, 205).name()
        glow = QColor.fromHsv(hue, 255, 255).name()
        return top, bottom, glow

    def _paint_notes(
        self, painter: QPainter, width: float, line_y: float, layout: KeyboardLayout
    ) -> None:
        assert self._song is not None
        time = self._time
        speed = self._fall_speed
        lookahead = line_y / speed + 0.5
        earliest = time - self._max_duration - 0.1

        start_index = max(0, bisect.bisect_left(self._starts, earliest))
        end_index = min(len(self._starts), bisect.bisect_right(self._starts, time + lookahead))

        painter.save()
        painter.setClipRect(QRectF(0.0, 0.0, width, line_y))
        theme = self._theme

        for index in range(start_index, end_index):
            note = self._song.notes[index]
            if note.end < time:
                continue
            key = layout.key(note.pitch)
            if key is None:
                continue

            bottom = line_y - (note.start - time) * speed
            height = max(note.duration * speed, 5.0)
            top = bottom - height
            if bottom < -8.0 or top > line_y + 8.0:
                continue

            top_clip = max(top, -20.0)
            bottom_clip = min(bottom, line_y)
            if bottom_clip <= top_clip:
                continue

            rect = QRectF(
                key.x + max(1.0, key.width * 0.06),
                top_clip,
                max(key.width - 2.0 * max(1.0, key.width * 0.06), 2.0),
                bottom_clip - top_clip,
            )
            radius = min(6.0, rect.width() / 2.0, max(3.0, (bottom_clip - top_clip) / 2.0))

            top_color, bottom_color, glow_color = self._note_colors(note.pitch)
            velocity_alpha = int(150 + 105 * min(note.velocity / 127.0, 1.0))

            # Soft neon halo: three expanding translucent rims.
            for grow, alpha in ((7.0, 16), (4.0, 26), (2.0, 40)):
                halo = QColor(glow_color)
                halo.setAlpha(alpha)
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(halo)
                painter.drawRoundedRect(
                    rect.adjusted(-grow, -grow, grow, grow),
                    radius + grow * 0.6,
                    radius + grow * 0.6,
                )

            painter.setBrush(self._gradient_brush(top_color, bottom_color))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawRoundedRect(rect, radius, radius)

            border = QColor(theme.note_border)
            border.setAlpha(min(180, velocity_alpha))
            pen = QPen(border)
            pen.setWidthF(1.2)
            painter.setPen(pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRoundedRect(rect.adjusted(0.6, 0.6, -0.6, -0.6), radius, radius)

            # Glossy top edge.
            if rect.height() > 10.0:
                gloss = QColor(255, 255, 255, 60)
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(gloss)
                painter.drawRoundedRect(
                    QRectF(
                        rect.left() + 2.0,
                        rect.top() + 1.5,
                        rect.width() - 4.0,
                        min(3.0, rect.height() * 0.2),
                    ),
                    radius * 0.6,
                    radius * 0.6,
                )

            # A bright flash while the note is being hit.
            if note.start <= time <= note.end:
                flash = QColor(255, 255, 255, 70)
                painter.setBrush(flash)
                painter.setPen(Qt.PenStyle.NoPen)
                painter.drawRoundedRect(
                    QRectF(rect.left(), line_y - 10.0, rect.width(), 10.0), radius, radius
                )

        painter.restore()
        self._update_pressed_keys(time)

    def _update_pressed_keys(self, time: float) -> None:
        assert self._song is not None
        pressed: set[int] = set()
        lowest = max(0, bisect.bisect_left(self._starts, time - self._max_duration - 0.1))
        highest = bisect.bisect_right(self._starts, time)
        for index in range(lowest, highest):
            note = self._song.notes[index]
            if note.start <= time <= note.end:
                pressed.add(note.pitch)
        new_hits = pressed - self._pressed
        self._pressed = pressed
        for pitch in new_hits:
            self.note_pressed.emit(pitch)

    def _paint_hit_line(self, painter: QPainter, width: float, line_y: float) -> None:
        theme = self._theme
        band = QLinearGradient(0.0, line_y - 26.0, 0.0, line_y + 10.0)
        c0 = QColor(theme.line_glow)
        c0.setAlpha(0)
        c1 = QColor(theme.line_glow)
        c1.setAlpha(70)
        c2 = QColor(theme.line_glow)
        c2.setAlpha(0)
        band.setColorAt(0.0, c0)
        band.setColorAt(0.75, c1)
        band.setColorAt(1.0, c2)
        painter.fillRect(QRectF(0.0, line_y - 26.0, width, 36.0), band)

        pen = QPen(QColor(theme.line))
        pen.setWidthF(2.0)
        painter.setPen(pen)
        painter.drawLine(QPointF(0.0, line_y), QPointF(width, line_y))

        pen.setWidthF(6.0)
        soft = QColor(theme.line)
        soft.setAlpha(50)
        pen.setColor(soft)
        painter.setPen(pen)
        painter.drawLine(QPointF(0.0, line_y), QPointF(width, line_y))

    # ... keyboard ---------------------------------------------------------
    def _paint_keyboard(
        self,
        painter: QPainter,
        width: float,
        height: float,
        line_y: float,
        piano_height: float,
        layout: KeyboardLayout,
    ) -> None:
        theme = self._theme
        pressed = self._pressed

        # Keyboard plate / shadow above the keys.
        plate = QLinearGradient(0.0, line_y, 0.0, line_y + 14.0)
        plate.setColorAt(0.0, QColor(0, 0, 0, 120))
        plate.setColorAt(1.0, QColor(0, 0, 0, 0))
        painter.fillRect(QRectF(0.0, line_y, width, 14.0), plate)

        label_font = self._font(max(9, int(piano_height * 0.085)), bold=True)
        painter.setFont(label_font)
        metrics = QFontMetrics(label_font)

        for key in layout.white_keys():
            is_down = key.pitch in pressed
            offset = 4.0 if is_down else 0.0
            rect = QRectF(
                key.x + 0.7,
                line_y + offset,
                key.width - 1.4,
                piano_height - offset - 1.0,
            )
            if is_down:
                brush = self._gradient_brush(theme.white_pressed_top, theme.white_pressed_bottom)
            else:
                brush = self._gradient_brush(theme.white_top, theme.white_bottom)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(brush)
            painter.drawRoundedRect(rect, 0.0, 0.0)

            # 3D bottom shadow / side shading.
            shadow = QColor(0, 0, 0, 26)
            painter.setBrush(shadow)
            painter.drawRect(QRectF(rect.left(), rect.bottom() - 4.0, rect.width(), 4.0))

            pen = QPen(QColor(theme.key_separator))
            pen.setWidthF(1.0)
            painter.setPen(pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawLine(QPointF(key.x, line_y), QPointF(key.x, height - 1.0))

            if key.pitch % 12 == 0:
                label = note_name(key.pitch)
                text_width = metrics.horizontalAdvance(label)
                if text_width < key.width - 4.0:
                    painter.setPen(QColor(theme.key_label))
                    painter.drawText(
                        QRectF(
                            key.x,
                            rect.bottom() - metrics.height() - 3.0,
                            key.width,
                            metrics.height(),
                        ),
                        Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter,
                        label,
                    )

        black_height = piano_height * 0.62
        for key in layout.black_keys():
            is_down = key.pitch in pressed
            offset = 3.0 if is_down else 0.0
            rect = QRectF(key.x, line_y, key.width, black_height + offset)
            if is_down:
                brush = self._gradient_brush(theme.black_pressed_top, theme.black_pressed_bottom)
            else:
                brush = self._gradient_brush(theme.black_top, theme.black_bottom)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(brush)
            painter.drawRoundedRect(rect, 4.0, 4.0)

            if not is_down:
                shine = QLinearGradient(0.0, line_y, 0.0, line_y + black_height * 0.45)
                shine.setColorAt(0.0, QColor(255, 255, 255, 38))
                shine.setColorAt(1.0, QColor(255, 255, 255, 0))
                painter.setBrush(shine)
                painter.drawRoundedRect(
                    QRectF(rect.left() + 1.5, line_y, max(rect.width() - 3.0, 1.0), black_height),
                    2.0,
                    2.0,
                )

        # Glow above pressed keys, spilling onto the waterfall.
        for key in layout.keys():
            if key.pitch not in pressed:
                continue
            glow = QRadialGradient(QPointF(key.center, line_y - 4.0), max(key.width * 2.2, 26.0))
            color = QColor(theme.line)
            color.setAlpha(70)
            glow.setColorAt(0.0, color)
            color2 = QColor(theme.line)
            color2.setAlpha(0)
            glow.setColorAt(1.0, color2)
            painter.setBrush(glow)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawEllipse(QPointF(key.center, line_y - 6.0), key.width * 1.6, 18.0)

    def _paint_particles(self, painter: QPainter, line_y: float) -> None:
        for particle in self._particles:
            alpha = int(180 * max(0.0, particle.life / particle.max_life))
            color = QColor(particle.color)
            color.setAlpha(alpha)
            painter.setBrush(color)
            painter.setPen(Qt.PenStyle.NoPen)
            radius = particle.radius * max(0.2, particle.life / particle.max_life)
            painter.drawEllipse(QPointF(particle.x, particle.y), radius, radius)

    def _spawn_hits(self, previous: float, current: float) -> None:
        if self._song is None or self._layout is None:
            return
        low = bisect.bisect_right(self._starts, previous)
        high = bisect.bisect_right(self._starts, current)
        line_y = float(self.height()) - self._piano_height(float(self.height()))
        for index in range(low, high):
            note = self._song.notes[index]
            key = self._layout.key(note.pitch)
            if key is None:
                continue
            top, _bottom, glow = self._note_colors(note.pitch)
            for _ in range(4):
                angle = math.radians(200 + (index * 37) % 140)
                speed = 30.0 + ((index * 53) % 45)
                self._particles.append(
                    Particle(
                        x=key.center,
                        y=line_y,
                        vx=math.cos(angle) * speed,
                        vy=math.sin(angle) * speed,
                        life=0.55,
                        max_life=0.55,
                        color=QColor(glow),
                        radius=1.6 + ((index * 17) % 20) / 20.0,
                    )
                )
        if len(self._particles) > 400:
            self._particles = self._particles[-400:]

    def _advance_particles(self, dt: float) -> None:
        if dt <= 0 or not self._particles:
            return
        dt = min(dt, 0.1)
        alive: list[Particle] = []
        for particle in self._particles:
            particle.life -= dt
            if particle.life <= 0:
                continue
            particle.vy += 260.0 * dt
            particle.x += particle.vx * dt
            particle.y += particle.vy * dt
            alive.append(particle)
        self._particles = alive

    # ... overlays ---------------------------------------------------------
    def _paint_empty_stage(
        self, painter: QPainter, width: float, height: float, line_y: float
    ) -> None:
        painter.save()
        painter.setPen(QPen(QColor(255, 255, 255, 18), 1.0, Qt.PenStyle.DashLine))
        painter.drawLine(QPointF(0.0, line_y), QPointF(width, line_y))
        painter.restore()

    def _paint_overlay(self, painter: QPainter, width: float, height: float) -> None:
        painter.save()
        panel_width = min(width * 0.62, 560.0)
        panel_height = 168.0 if self._overlay_progress is None else 196.0
        rect = QRectF(
            (width - panel_width) / 2.0,
            height * 0.42 - panel_height / 2.0,
            panel_width,
            panel_height,
        )

        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(10, 14, 22, 205))
        painter.drawRoundedRect(rect, 18.0, 18.0)

        border = QColor(self._theme.accent)
        border.setAlpha(110)
        painter.setPen(QPen(border, 1.2))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRoundedRect(rect, 18.0, 18.0)

        painter.setPen(QColor(self._theme.text))
        painter.setFont(self._font(19, bold=True))
        painter.drawText(
            QRectF(rect.left(), rect.top() + 26.0, rect.width(), 34.0),
            Qt.AlignmentFlag.AlignHCenter,
            self._overlay_title,
        )

        if self._overlay_subtitle:
            painter.setPen(QColor(255, 255, 255, 150))
            painter.setFont(self._font(12))
            painter.drawText(
                QRectF(rect.left() + 20.0, rect.top() + 66.0, rect.width() - 40.0, 46.0),
                Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop,
                self._overlay_subtitle,
            )

        if self._overlay_progress is not None:
            bar_width = rect.width() * 0.62
            bar_height = 6.0
            bar = QRectF(
                rect.center().x() - bar_width / 2.0,
                rect.bottom() - 34.0,
                bar_width,
                bar_height,
            )
            painter.setBrush(QColor(255, 255, 255, 26))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawRoundedRect(bar, 3.0, 3.0)

            filled = QRectF(bar)
            filled.setWidth(bar_width * max(0.02, min(self._overlay_progress, 1.0)))
            accent = QColor(self._theme.accent)
            painter.setBrush(accent)
            painter.drawRoundedRect(filled, 3.0, 3.0)
        painter.restore()

    # ... interaction ------------------------------------------------------
    def mouseDoubleClickEvent(self, event) -> None:  # noqa: N802
        window = self.window()
        if window is not None:
            if window.isFullScreen():
                window.showNormal()
            else:
                window.showFullScreen()
        super().mouseDoubleClickEvent(event)

    def resizeEvent(self, event) -> None:  # noqa: N802
        self._layout = None
        self._layout_width = 0
        super().resizeEvent(event)
