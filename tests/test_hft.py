from __future__ import annotations

import numpy as np
import pytest

from piano_waterfall import hft


def test_model_is_bundled() -> None:
    path = hft.model_path()
    assert path is not None and path.is_file()
    assert path.stat().st_size > 20_000_000
    available, detail = hft.availability()
    assert available is True
    assert "hFT" in detail


def test_mel_spectrogram_shape_and_finiteness() -> None:
    sample_rate = hft.SAMPLE_RATE
    t = np.arange(sample_rate, dtype=np.float32) / sample_rate
    wave = 0.3 * np.sin(2 * np.pi * 440.0 * t).astype(np.float32)
    feature = hft.mel_spectrogram(wave)
    assert feature.shape[1] == hft.N_MELS
    assert feature.shape[0] == 1 + sample_rate // hft.HOP_SAMPLE
    assert np.isfinite(feature).all()


def test_decode_notes_basic() -> None:
    frames = 100
    onset = np.zeros((frames, hft.NUM_NOTE), dtype=np.float32)
    offset = np.zeros_like(onset)
    mpe = np.ones_like(onset)
    velocity = np.full((frames, hft.NUM_NOTE), 80, dtype=np.int8)
    onset[10, 39] = 0.9
    offset[40, 39] = 0.9
    notes = hft.decode_notes(onset, offset, mpe, velocity)
    assert len(notes) == 1
    note = notes[0]
    assert note["pitch"] == 60
    assert note["velocity"] == 80
    assert abs(note["onset"] - 10 * hft.HOP_SAMPLE / hft.SAMPLE_RATE) < 0.02
    assert note["offset"] > note["onset"]


def test_decode_notes_uses_peak_end_when_no_offset() -> None:
    frames = 80
    onset = np.zeros((frames, hft.NUM_NOTE), dtype=np.float32)
    offset = np.zeros_like(onset)
    mpe = np.ones_like(onset)
    velocity = np.full((frames, hft.NUM_NOTE), 90, dtype=np.int8)
    onset[5, 20] = 0.8
    mpe[30, 20] = 0.0
    notes = hft.decode_notes(onset, offset, mpe, velocity)
    assert len(notes) == 1
    assert notes[0]["pitch"] == 41
    assert abs(notes[0]["offset"] - 30 * hft.HOP_SAMPLE / hft.SAMPLE_RATE) < 0.02


def test_write_midi_roundtrip(tmp_path) -> None:
    import mido

    notes = [
        {"pitch": 60, "onset": 0.0, "offset": 0.5, "velocity": 80},
        {"pitch": 64, "onset": 0.5, "offset": 1.0, "velocity": 90},
    ]
    path = hft.write_midi(notes, tmp_path / "out.mid")
    data = mido.MidiFile(path)
    messages = [msg for track in data.tracks for msg in track]
    ons = [msg for msg in messages if msg.type == "note_on" and msg.velocity]
    offs = [msg for msg in messages if msg.type == "note_off"]
    assert len(ons) == 2
    assert len(offs) == 2
    assert {msg.note for msg in ons} == {60, 64}


def test_download_model_writes_file(monkeypatch, tmp_path) -> None:
    class FakeResponse:
        headers = {"Content-Length": "9"}

        def __init__(self):
            self.chunks = [b"abc", b"def", b"ghi"]

        def read(self, _size):
            return self.chunks.pop(0) if self.chunks else b""

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    monkeypatch.setenv("PIANO_WATERFALL_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setattr(hft.urllib.request, "urlopen", lambda *a, **k: FakeResponse())
    seen = []
    path = hft.download_model(progress=lambda done, total: seen.append((done, total)))
    assert path.read_bytes() == b"abcdefghi"
    assert path.parent.name == "models"
    assert seen[-1] == (9, 9)


def test_transcribe_requires_model(monkeypatch, tmp_path) -> None:
    audio = tmp_path / "input.wav"
    audio.write_bytes(b"RIFF")
    monkeypatch.setattr(hft, "model_path", lambda: None)
    with pytest.raises(hft.TranscriptionUnavailable):
        hft.transcribe(audio, tmp_path / "out.mid")
