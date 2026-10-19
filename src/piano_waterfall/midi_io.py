"""MIDI reading and normalisation.

The visualiser only needs three things from a MIDI file: which pitch is
played, when it starts, and how long it lasts (in seconds).  Everything else
(tempo maps, multiple tracks, meta events) is handled by ``mido``'s merged
iterator, which already converts ticks to wall-clock seconds using the tempo
map of the file.
"""

from __future__ import annotations

import math
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from pathlib import Path

import mido

#: MIDI note number of A0 / C8 – the range of a standard 88-key piano.
MIN_PIANO_PITCH = 21
MAX_PIANO_PITCH = 108

#: Percussion channel (0-based) in General MIDI.
DRUM_CHANNEL = 9

#: Pitch classes that are black keys.
BLACK_PITCH_CLASSES = frozenset({1, 3, 6, 8, 10})


@dataclass(frozen=True, slots=True)
class Note:
    """A single piano note, times in seconds from the start of the song."""

    pitch: int
    start: float
    duration: float
    velocity: int = 90
    channel: int = 0

    @property
    def end(self) -> float:
        return self.start + self.duration

    @property
    def is_black(self) -> bool:
        return self.pitch % 12 in BLACK_PITCH_CLASSES


@dataclass(slots=True)
class Song:
    """A parsed song, ready for playback and rendering."""

    notes: list[Note]
    duration: float
    source: Path | None = None
    title: str = ""
    tempo_bpm: float = 120.0
    sustain_segments: list[tuple[float, float]] = field(default_factory=list)

    @property
    def note_count(self) -> int:
        return len(self.notes)

    @property
    def pitch_range(self) -> tuple[int, int]:
        if not self.notes:
            return (60, 60)
        pitches = [n.pitch for n in self.notes]
        return (min(pitches), max(pitches))

    @property
    def first_note_start(self) -> float:
        return min((n.start for n in self.notes), default=0.0)

    def iter_active(self, time: float) -> Iterable[Note]:
        for note in self.notes:
            if note.start <= time < note.end:
                yield note


class MidiError(RuntimeError):
    """Raised when a file cannot be parsed as MIDI."""


def parse_midi(
    path: str | Path,
    *,
    include_percussion: bool = False,
    apply_sustain: bool = True,
    limit_seconds: float | None = None,
) -> Song:
    """Read ``path`` and return a normalised :class:`Song`.

    Parameters
    ----------
    include_percussion:
        Keep channel 10 (index 9) notes.  Off by default because a piano
        waterfall for drum hits looks like nonsense.
    apply_sustain:
        Extend note lengths across sustain-pedal (CC64) segments.
    limit_seconds:
        Drop everything after this many seconds (useful for previews).
    """

    path = Path(path)
    try:
        midi = mido.MidiFile(str(path))
    except Exception as exc:  # mido raises different errors for bad files
        raise MidiError(f"无法解析 MIDI 文件：{path.name}（{exc}）") from exc

    active: dict[tuple[int, int], list[tuple[float, int, int]]] = {}
    notes: list[Note] = []
    pedal_segments: list[tuple[float, float]] = []
    pedal_start: float | None = None
    now = 0.0

    for msg in midi:
        now += float(msg.time)
        if limit_seconds is not None and now > limit_seconds:
            break

        if msg.type == "note_on" and msg.velocity > 0:
            if msg.channel == DRUM_CHANNEL and not include_percussion:
                continue
            active.setdefault((msg.channel, msg.note), []).append((now, msg.velocity, msg.channel))
        elif msg.type == "note_off" or (msg.type == "note_on" and msg.velocity == 0):
            stack = active.get((msg.channel, msg.note))
            if stack:
                start, velocity, channel = stack.pop(0)
                notes.append(
                    Note(
                        pitch=msg.note,
                        start=start,
                        duration=max(now - start, 0.01),
                        velocity=velocity,
                        channel=channel,
                    )
                )
        elif msg.type == "control_change" and msg.control == 64:
            if msg.value >= 64 and pedal_start is None:
                pedal_start = now
            elif msg.value < 64 and pedal_start is not None:
                pedal_segments.append((pedal_start, now))
                pedal_start = None

    if pedal_start is not None:
        pedal_segments.append((pedal_start, now))

    # Close notes that were never released (truncated files, stuck notes).
    for (_channel, pitch), stack in active.items():
        for start, velocity, channel in stack:
            notes.append(
                Note(
                    pitch=pitch,
                    start=start,
                    duration=max(now - start, 0.01),
                    velocity=velocity,
                    channel=channel,
                )
            )

    notes.sort(key=lambda n: (n.start, n.pitch))

    if apply_sustain and pedal_segments:
        notes = _apply_sustain(notes, pedal_segments, now)

    duration = max((n.end for n in notes), default=0.0)
    duration = max(duration, float(midi.length))
    if limit_seconds is not None:
        duration = min(duration, limit_seconds)

    return Song(
        notes=notes,
        duration=duration,
        source=path,
        title=path.stem,
        tempo_bpm=_estimate_tempo(midi),
        sustain_segments=pedal_segments,
    )


def _apply_sustain(
    notes: Sequence[Note], segments: Sequence[tuple[float, float]], song_end: float
) -> list[Note]:
    """Extend notes that are held by the sustain pedal."""

    result: list[Note] = []
    for note in notes:
        end = note.end
        for seg_start, seg_end in segments:
            # A key released while the damper pedal is down keeps ringing
            # until the pedal is lifted, no matter when the key went down.
            if seg_start <= note.end <= seg_end:
                end = max(end, min(seg_end, song_end))
        if end > note.end:
            result.append(
                Note(
                    pitch=note.pitch,
                    start=note.start,
                    duration=end - note.start,
                    velocity=note.velocity,
                    channel=note.channel,
                )
            )
        else:
            result.append(note)
    return result


def _estimate_tempo(midi: mido.MidiFile) -> float:
    tempos = [msg.tempo for track in midi.tracks for msg in track if msg.type == "set_tempo"]
    if not tempos:
        return 120.0
    return round(60_000_000 / tempos[0], 1)


def format_time(seconds: float) -> str:
    """``83.4`` -> ``"01:23"``."""

    seconds = max(0.0, float(seconds))
    minutes = int(seconds // 60)
    rest = int(round(seconds - minutes * 60))
    if rest == 60:
        minutes += 1
        rest = 0
    return f"{minutes:02d}:{rest:02d}"


def note_name(pitch: int) -> str:
    names = ("C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B")
    octave = pitch // 12 - 1
    return f"{names[pitch % 12]}{octave}"


def midi_frequency(pitch: int) -> float:
    return 440.0 * math.pow(2.0, (pitch - 69) / 12.0)
