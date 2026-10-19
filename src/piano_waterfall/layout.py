"""Keyboard geometry for the waterfall view.

The layout is deliberately pure Python (no Qt) so it can be unit-tested and
reused by the offline renderer.  Widths are floats; the widget converts to
integer pixels when painting.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass

from .midi_io import BLACK_PITCH_CLASSES, MAX_PIANO_PITCH, MIN_PIANO_PITCH


@dataclass(frozen=True, slots=True)
class Key:
    pitch: int
    x: float
    width: float
    black: bool

    @property
    def center(self) -> float:
        return self.x + self.width / 2.0


class KeyboardLayout:
    """Maps pitches to horizontal positions for a given viewport width."""

    __slots__ = (
        "min_pitch",
        "max_pitch",
        "width",
        "white_width",
        "black_width",
        "_white_index",
        "white_count",
        "_white_pitches",
    )

    def __init__(self, min_pitch: int, max_pitch: int, width: float) -> None:
        if max_pitch <= min_pitch:
            max_pitch = min_pitch + 12
        self.min_pitch = int(min_pitch)
        self.max_pitch = int(max_pitch)
        self.width = float(width)

        whites = [
            pitch
            for pitch in range(self.min_pitch, self.max_pitch + 1)
            if pitch % 12 not in BLACK_PITCH_CLASSES
        ]
        self.white_count = len(whites)
        self.white_width = self.width / max(self.white_count, 1)
        self.black_width = self.white_width * 0.62
        self._white_index = {pitch: i for i, pitch in enumerate(whites)}
        self._white_pitches = whites

    def key(self, pitch: int) -> Key | None:
        if not (self.min_pitch <= pitch <= self.max_pitch):
            return None
        if pitch % 12 in BLACK_PITCH_CLASSES:
            boundary = 0
            for p in range(self.min_pitch, pitch):
                if p % 12 not in BLACK_PITCH_CLASSES:
                    boundary += 1
            x = boundary * self.white_width - self.black_width / 2.0
            x = min(max(x, 0.0), self.width - self.black_width)
            return Key(pitch, x, self.black_width, True)
        index = self._white_index[pitch]
        return Key(pitch, index * self.white_width, self.white_width, False)

    def keys(self) -> Iterator[Key]:
        for pitch in range(self.min_pitch, self.max_pitch + 1):
            key = self.key(pitch)
            if key is not None:
                yield key

    def white_keys(self) -> list[Key]:
        return [k for k in self.keys() if not k.black]

    def black_keys(self) -> list[Key]:
        return [k for k in self.keys() if k.black]

    def pitch_at(self, x: float) -> int | None:
        """Return the pitch under a horizontal position (black keys win)."""

        if not (0.0 <= x <= self.width):
            return None
        for key in self.black_keys():
            if key.x <= x <= key.x + key.width:
                return key.pitch
        index = min(max(int(x / self.white_width), 0), self.white_count - 1)
        return self._white_pitches[index]


def fit_keyboard_range(low: int, high: int) -> tuple[int, int]:
    """Choose a pleasant, C-aligned keyboard range covering ``low..high``.

    The range is padded to whole octaves and always spans at least three
    octaves so that a melody-only file does not produce comically wide keys.
    """

    low = max(MIN_PIANO_PITCH, int(low))
    high = min(MAX_PIANO_PITCH, int(high))
    if high < low:
        low, high = high, low

    while high - low < 36:
        if low > MIN_PIANO_PITCH:
            low -= 12
        if high - low < 36 and high < MAX_PIANO_PITCH:
            high += 12
        if low <= MIN_PIANO_PITCH and high >= MAX_PIANO_PITCH:
            break

    # Align the bottom to a C (or to A0 for the very bottom of the piano).
    low -= low % 12
    low = max(low, MIN_PIANO_PITCH)
    # Align the top to a C, leaving a little air above the highest note.
    if high % 12:
        high += 12 - high % 12
    high = min(high, MAX_PIANO_PITCH)

    if low == high:
        high = min(low + 12, MAX_PIANO_PITCH)
    return low, high
