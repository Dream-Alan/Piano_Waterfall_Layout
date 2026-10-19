from __future__ import annotations

from piano_waterfall.paths import (
    DATA_DIR_ENV,
    app_data_dir,
    audio_cache_dir,
    cached_audio_path,
    transcriptions_dir,
)
from piano_waterfall.synth import SynthSettings


def test_data_dir_environment_override(monkeypatch, tmp_path) -> None:
    target = tmp_path / "portable" / "data"
    monkeypatch.setenv(DATA_DIR_ENV, str(target))

    assert app_data_dir() == target
    assert target.is_dir()
    assert audio_cache_dir() == target / "audio-cache"
    assert audio_cache_dir().is_dir()
    assert transcriptions_dir() == target / "transcriptions"


def test_cached_audio_path_is_stable_and_settings_aware(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv(DATA_DIR_ENV, str(tmp_path / "data"))
    midi = tmp_path / "song.mid"
    midi.write_bytes(b"MFake midi bytes")

    first = cached_audio_path(midi, SynthSettings())
    again = cached_audio_path(midi, SynthSettings())
    other = cached_audio_path(midi, SynthSettings(max_harmonics=6))

    assert first == again
    assert first != other
    assert first.parent == tmp_path / "data" / "audio-cache"
    assert first.name.startswith("song-")
    assert first.suffix == ".wav"


def test_cached_audio_path_for_missing_file(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv(DATA_DIR_ENV, str(tmp_path / "data"))
    path = cached_audio_path(tmp_path / "missing.mid", SynthSettings())
    assert path.name.startswith("missing-")
