from __future__ import annotations

from PySide6.QtGui import QImage

from piano_waterfall.midi_io import Note, Song
from piano_waterfall.waterfall import WaterfallWidget


def test_widget_paints_a_song(qapp) -> None:
    widget = WaterfallWidget()
    widget.resize(900, 600)
    song = Song(
        notes=[Note(pitch, i * 0.05, 0.4, velocity=100) for i, pitch in enumerate(range(60, 72))],
        duration=2.0,
    )
    widget.set_song(song, title="test.mid")
    widget.set_time(0.6)

    image = QImage(900, 600, QImage.Format.Format_ARGB32)
    image.fill(0)
    widget.render(image)

    colors = {image.pixel(x, y) for x in range(0, 900, 17) for y in range(0, 600, 13)}
    assert len(colors) > 10
    assert image.pixelColor(450, 590).lightness() > 20  # keyboard is drawn


def test_widget_handles_empty_song(qapp) -> None:
    widget = WaterfallWidget()
    widget.resize(640, 400)
    widget.set_time(0.0)
    image = QImage(640, 400, QImage.Format.Format_ARGB32)
    image.fill(0)
    widget.render(image)
    assert image.width() == 640


def test_fall_speed_and_theme_are_clamped(qapp) -> None:
    widget = WaterfallWidget()
    widget.set_fall_speed(-100)
    assert widget.fall_speed >= 100
    widget.set_fall_speed(99_999)
    assert widget.fall_speed <= 2000
    widget.set_rainbow(True)
    assert widget._rainbow is True
