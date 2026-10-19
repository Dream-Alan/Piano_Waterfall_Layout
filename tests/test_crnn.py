from __future__ import annotations

import numpy as np
import pytest

from piano_waterfall import crnn, transcribe


def _blank(frames: int = 200) -> dict[str, np.ndarray]:
    zeros = np.zeros((frames, crnn.NUM_NOTE), dtype=np.float32)
    return {
        "onset": zeros.copy(),
        "offset": zeros.copy(),
        "frame": zeros.copy(),
        "velocity": zeros.copy(),
    }


def test_decode_uses_offset_regression() -> None:
    data = _blank()
    pitch = 60 - crnn.NOTE_MIN
    data["onset"][10, pitch] = 0.9
    data["frame"][10:21, pitch] = 0.6
    data["offset"][20, pitch] = 0.8
    data["velocity"][10, pitch] = 0.8

    notes = crnn.decode(data["onset"], data["offset"], data["frame"], data["velocity"])

    assert len(notes) == 1
    note = notes[0]
    assert note["pitch"] == 60
    assert note["onset"] == pytest.approx(0.10)
    assert note["offset"] == pytest.approx(0.20)
    assert note["velocity"] == pytest.approx(102, abs=1)


def test_decode_falls_back_to_frame_silence() -> None:
    data = _blank()
    pitch = 64 - crnn.NOTE_MIN
    data["onset"][30, pitch] = 0.9
    data["frame"][30:46, pitch] = 0.7
    data["velocity"][30, pitch] = 0.5

    notes = crnn.decode(data["onset"], data["offset"], data["frame"], data["velocity"])

    assert len(notes) == 1
    assert notes[0]["pitch"] == 64
    # The frame activation goes quiet at frame 46, two frames after this.
    assert notes[0]["offset"] >= 0.46
    assert notes[0]["offset"] <= 0.52


def test_decode_drops_too_short_notes() -> None:
    data = _blank()
    pitch = 72 - crnn.NOTE_MIN
    data["onset"][10, pitch] = 0.9
    data["offset"][9, pitch] = 0.0
    data["frame"][10:11, pitch] = 0.5

    notes = crnn.decode(data["onset"], data["offset"], data["frame"], data["velocity"])

    assert notes == []


def test_engine_registry() -> None:
    assert transcribe.ENGINES == ("hft", "crnn")
    assert set(transcribe.ENGINE_NAMES) == set(transcribe.ENGINES)
    assert transcribe.DEFAULT_ENGINE == "hft"


def test_unknown_engine_is_rejected() -> None:
    with pytest.raises(ValueError):
        transcribe.transcribe("in.wav", "out.mid", engine="nope")


def test_crnn_model_env_override(tmp_path, monkeypatch) -> None:
    model = tmp_path / "piano_crnn.onnx"
    monkeypatch.setenv(crnn.MODEL_ENV, str(model))

    model.write_bytes(b"partial")
    assert crnn.model_path() is None

    with model.open("r+b") as handle:
        handle.truncate(50_000_001)
    assert crnn.model_path() == model
    available, detail = crnn.availability()
    assert available is True
    assert "CRNN" in detail
