from __future__ import annotations

import math
from pathlib import Path

import mido
import pytest

from piano_waterfall.midi_io import (
    MidiError,
    Note,
    Song,
    format_time,
    midi_frequency,
    note_name,
    parse_midi,
)

TICKS_PER_SECOND = 960  # ticks_per_beat=480 at 120 BPM


def _write_midi(tmp_path: Path, events: list[tuple[mido.Message, float]]) -> Path:
    midi = mido.MidiFile(type=0, ticks_per_beat=480)
    track = mido.MidiTrack()
    midi.tracks.append(track)
    track.append(mido.MetaMessage("set_tempo", tempo=mido.bpm2tempo(120), time=0))
    for message, delta_seconds in events:
        track.append(message.copy(time=int(round(delta_seconds * TICKS_PER_SECOND))))
    path = tmp_path / "song.mid"
    midi.save(path)
    return path


def test_parses_simple_note(tmp_path: Path) -> None:
    path = _write_midi(
        tmp_path,
        [
            (mido.Message("note_on", note=60, velocity=100), 0.0),
            (mido.Message("note_off", note=60, velocity=0), 0.5),
        ],
    )
    song = parse_midi(path)
    assert song.note_count == 1
    note = song.notes[0]
    assert note.pitch == 60
    assert note.start == pytest.approx(0.0, abs=0.01)
    assert note.duration == pytest.approx(0.5, abs=0.01)
    assert note.velocity == 100
    assert song.tempo_bpm == 120.0
    assert song.duration >= 0.5
    assert song.source == path
    assert song.title == "song"


def test_note_on_with_zero_velocity_counts_as_note_off(tmp_path: Path) -> None:
    path = _write_midi(
        tmp_path,
        [
            (mido.Message("note_on", note=64, velocity=90), 0.0),
            (mido.Message("note_on", note=64, velocity=0), 0.25),
        ],
    )
    song = parse_midi(path)
    assert song.note_count == 1
    assert song.notes[0].duration == pytest.approx(0.25, abs=0.01)


def test_percussion_is_skipped_by_default(tmp_path: Path) -> None:
    path = _write_midi(
        tmp_path,
        [
            (mido.Message("note_on", channel=9, note=38, velocity=100), 0.0),
            (mido.Message("note_off", channel=9, note=38), 0.4),
        ],
    )
    assert parse_midi(path).note_count == 0
    assert parse_midi(path, include_percussion=True).note_count == 1


def test_sustain_pedal_extends_released_notes(tmp_path: Path) -> None:
    path = _write_midi(
        tmp_path,
        [
            (mido.Message("note_on", note=60, velocity=90), 0.0),
            (mido.Message("control_change", control=64, value=127), 0.1),
            (mido.Message("note_off", note=60), 0.1),
            (mido.Message("control_change", control=64, value=0), 0.4),
        ],
    )
    song = parse_midi(path)
    assert song.notes[0].duration == pytest.approx(0.6, abs=0.02)
    segment = song.sustain_segments[0]
    assert segment[0] == pytest.approx(0.1, abs=0.02)
    assert segment[1] == pytest.approx(0.6, abs=0.02)

    dry = parse_midi(path, apply_sustain=False)
    assert dry.notes[0].duration == pytest.approx(0.2, abs=0.02)


def test_pedal_after_release_does_not_extend(tmp_path: Path) -> None:
    path = _write_midi(
        tmp_path,
        [
            (mido.Message("note_on", note=60), 0.0),
            (mido.Message("note_off", note=60), 0.2),
            (mido.Message("control_change", control=64, value=127), 0.1),
            (mido.Message("control_change", control=64, value=0), 0.1),
        ],
    )
    song = parse_midi(path)
    assert song.notes[0].duration == pytest.approx(0.2, abs=0.02)


def test_unterminated_note_is_closed(tmp_path: Path) -> None:
    path = _write_midi(
        tmp_path,
        [(mido.Message("note_on", note=72, velocity=80), 0.0)],
    )
    song = parse_midi(path)
    assert song.note_count == 1
    assert song.notes[0].duration == pytest.approx(0.01, abs=0.001)


def test_limit_seconds_truncates(tmp_path: Path) -> None:
    path = _write_midi(
        tmp_path,
        [
            (mido.Message("note_on", note=60), 0.0),
            (mido.Message("note_off", note=60), 2.0),
        ],
    )
    song = parse_midi(path, limit_seconds=1.0)
    assert song.duration <= 1.0


def test_invalid_file_raises(tmp_path: Path) -> None:
    path = tmp_path / "broken.mid"
    path.write_text("definitely not midi", encoding="utf-8")
    with pytest.raises(MidiError):
        parse_midi(path)


def test_time_and_note_helpers() -> None:
    assert format_time(0) == "00:00"
    assert format_time(-5) == "00:00"
    assert format_time(83.4) == "01:23"
    assert format_time(59.6) == "01:00"
    assert format_time(3600) == "60:00"
    assert note_name(21) == "A0"
    assert note_name(60) == "C4"
    assert note_name(61) == "C#4"
    assert note_name(108) == "C8"
    assert midi_frequency(69) == pytest.approx(440.0)
    assert midi_frequency(60) == pytest.approx(261.63, abs=0.01)


def test_song_properties_and_active_notes() -> None:
    song = Song(
        notes=[
            Note(60, 0.0, 1.0),
            Note(64, 0.5, 1.0),
            Note(67, 1.5, 0.5),
        ],
        duration=2.0,
    )
    assert song.note_count == 3
    assert song.pitch_range == (60, 67)
    assert song.first_note_start == 0.0
    assert [n.pitch for n in song.iter_active(0.6)] == [60, 64]
    assert [n.pitch for n in song.iter_active(1.5)] == [67]
    assert list(song.iter_active(5.0)) == []
    assert Note(61, 0.0, 1.0).is_black
    assert not Note(60, 0.0, 1.0).is_black
    assert Note(60, 1.0, 0.5).end == pytest.approx(1.5)
    assert math.isclose(midi_frequency(81), 880.0)
