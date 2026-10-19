from __future__ import annotations

import numpy as np
import pytest

from piano_waterfall.midi_io import Note, Song
from piano_waterfall.synth import (
    DEFAULT_SETTINGS,
    RenderCancelled,
    SynthSettings,
    render_song,
    write_wav,
)

TINY = SynthSettings(sample_rate=22_050, max_harmonics=5, reverb=0.2, tail=0.4)


def _song() -> Song:
    return Song(
        notes=[Note(60, 0.0, 0.2, 100), Note(64, 0.1, 0.3, 80), Note(67, 0.2, 0.2, 60)],
        duration=0.5,
    )


def test_render_song_shape_and_dtype() -> None:
    audio = render_song(_song(), TINY)
    assert audio.dtype == np.float32
    assert audio.ndim == 2 and audio.shape[1] == 2
    expected = int((0.5 + 0.4) * TINY.sample_rate) + 1
    assert audio.shape[0] == expected
    assert np.isfinite(audio).all()
    assert float(np.max(np.abs(audio))) <= 1.0
    assert float(np.sqrt(np.mean(audio**2))) > 0.001


def test_render_song_progress_messages() -> None:
    seen: list[tuple[float, str]] = []
    render_song(_song(), TINY, progress=lambda f, m: seen.append((f, m)))
    assert seen
    assert seen[-1][0] == 1.0
    assert "完成" in seen[-1][1]


def test_render_song_can_be_cancelled() -> None:
    with pytest.raises(RenderCancelled):
        render_song(_song(), TINY, should_cancel=lambda: True)


def test_empty_song_renders_one_second_of_silence() -> None:
    audio = render_song(Song(notes=[], duration=0.0), TINY)
    assert audio.shape == (TINY.sample_rate, 2)
    assert not audio.any()


def test_default_settings_are_sane() -> None:
    assert DEFAULT_SETTINGS.sample_rate == 44_100
    assert DEFAULT_SETTINGS.channels == 2
    assert 0 < DEFAULT_SETTINGS.normalize <= 1


def test_write_wav_accepts_part_suffix(tmp_path) -> None:
    """The renderer writes to ``*.wav.part`` before renaming (regression)."""

    import soundfile as sf

    audio = render_song(_song(), TINY)
    target = tmp_path / "audio.wav.part"
    write_wav(target, audio, TINY.sample_rate)
    assert target.exists() and target.stat().st_size > 1000
    info = sf.info(str(target))
    assert info.samplerate == TINY.sample_rate
    assert info.channels == 2
    assert info.format == "WAV"
