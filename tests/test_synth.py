from __future__ import annotations

from dataclasses import replace

import numpy as np
import pytest

from piano_waterfall.midi_io import Note, Song
from piano_waterfall.samples import (
    SAMPLES_ENV,
    SampleBankMissing,
    bank,
    clear_cache,
    sample_for,
)
from piano_waterfall.synth import (
    DEFAULT_SETTINGS,
    DEFAULT_VOICE,
    VOICES,
    RenderCancelled,
    SynthSettings,
    get_voice,
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
    assert DEFAULT_SETTINGS.voice == DEFAULT_VOICE


def _centroid(audio: np.ndarray, sample_rate: int) -> float:
    mono = audio.mean(axis=1)
    spectrum = np.abs(np.fft.rfft(mono))
    freqs = np.fft.rfftfreq(len(mono), 1.0 / sample_rate)
    return float((spectrum * freqs).sum() / max(spectrum.sum(), 1e-9))


def test_voice_presets_are_well_defined() -> None:
    assert DEFAULT_VOICE in VOICES
    assert len(VOICES) >= 5
    for key, voice in VOICES.items():
        assert voice.key == key
        assert voice.name and voice.description
        assert voice.lowpass_hz is None or 400 <= voice.lowpass_hz <= 8000
        assert -12 <= voice.high_shelf_db <= 12
        assert -12 <= voice.low_shelf_db <= 12
        assert 0.0005 <= voice.attack <= 0.03
        assert 0.04 <= voice.release <= 0.4
        assert 0 <= voice.presence_db <= 8
        assert voice.gain > 0


def test_unknown_voice_falls_back_to_default() -> None:
    assert get_voice("does-not-exist").key == DEFAULT_VOICE
    assert get_voice(None).key == DEFAULT_VOICE


def test_voice_changes_the_rendered_timbre() -> None:
    bright = render_song(_song(), replace(TINY, voice="bright"))
    felt = render_song(_song(), replace(TINY, voice="felt"))
    assert bright.shape == felt.shape
    assert not np.allclose(bright, felt, atol=1e-4)
    assert _centroid(bright, TINY.sample_rate) > _centroid(felt, TINY.sample_rate) * 1.3


def test_every_voice_renders() -> None:
    for key in VOICES:
        audio = render_song(_song(), replace(TINY, voice=key))
        assert np.isfinite(audio).all()
        assert float(np.max(np.abs(audio))) > 0.001


def test_bundled_sample_bank_covers_piano_range() -> None:
    mapping, roots = bank()
    assert len(roots) >= 20
    assert roots[0] <= 36
    assert roots[-1] >= 96
    assert all(path.exists() for path in mapping.values())


def test_sample_for_transposes_and_stays_finite() -> None:
    root = sample_for(60, 22_050)
    higher = sample_for(61, 22_050)
    lower = sample_for(59, 22_050)
    assert root.size > 1000
    assert higher.size < root.size < lower.size
    assert np.isfinite(higher).all() and np.isfinite(lower).all()


def test_missing_bank_raises(monkeypatch, tmp_path) -> None:
    clear_cache()
    monkeypatch.setenv(SAMPLES_ENV, str(tmp_path / "empty"))
    try:
        with pytest.raises(SampleBankMissing):
            bank()
    finally:
        clear_cache()


def test_write_wav_accepts_part_suffix(tmp_path) -> None:
    """The renderer writes to ``*.wav.part`` before renaming (regression)."""

    import wave

    audio = render_song(_song(), TINY)
    target = tmp_path / "audio.wav.part"
    write_wav(target, audio, TINY.sample_rate)
    assert target.exists() and target.stat().st_size > 1000
    with wave.open(str(target), "rb") as handle:
        assert handle.getframerate() == TINY.sample_rate
        assert handle.getnchannels() == 2
        assert handle.getsampwidth() == 2
        assert handle.getnframes() == audio.shape[0]
