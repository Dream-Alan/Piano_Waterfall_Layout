"""High-accuracy transcription with the CRNN piano model.

The "fast" engine bundled with Piano Waterfall is Sony's hFT-Transformer
(22 MB).  This module adds an optional "high accuracy" engine based on the
MIT-licensed Kong et al. CRNN model, exported to ONNX by the
``stelee/piano-transcription-onnx`` project (154 MB).

The model runs on 10-second audio segments at 16 kHz and predicts onset,
offset, frame and velocity activations at 100 frames per second.  Notes are
decoded from those activations; the result is written with the shared MIDI
writer in :mod:`piano_waterfall.hft`.
"""

from __future__ import annotations

import os
import urllib.request
from collections.abc import Callable
from pathlib import Path

import numpy as np

from . import hft
from .paths import app_data_dir

ProgressFn = Callable[[float, str], None]
CancelFn = Callable[[], bool]

SAMPLE_RATE = 16_000
SEGMENT_SECONDS = 10.0
HOP_SECONDS = 5.0
SEGMENT_SAMPLES = int(SEGMENT_SECONDS * SAMPLE_RATE)
HOP_SAMPLES = int(HOP_SECONDS * SAMPLE_RATE)
NUM_FRAMES = 1001
NUM_NOTE = 88
NOTE_MIN = 21
FRAMES_PER_SECOND = 100.0

ONSET_THRESHOLD = 0.3
OFFSET_THRESHOLD = 0.3
FRAME_THRESHOLD = 0.1
MIN_DURATION = 0.03

MODEL_NAME = "piano_crnn.onnx"
MODEL_SIZE_HINT = 154
MODEL_ENV = "PIANO_WATERFALL_CRNN_MODEL"
MODEL_URLS = (
    "https://github.com/Dream-Alan/Piano_Waterfall_Layout/releases/download/"
    "models-v1/piano_crnn.onnx",
    "https://hf-mirror.com/stelee/piano-transcription-onnx/resolve/main/piano_crnn.onnx",
)

TranscriptionUnavailable = hft.TranscriptionUnavailable
TranscriptionCancelled = hft.TranscriptionCancelled


def model_path() -> Path | None:
    """Return the downloaded high-accuracy model, if present."""

    override = os.environ.get(MODEL_ENV)
    candidates = [Path(override)] if override else []
    candidates.append(app_data_dir() / "models" / MODEL_NAME)
    for candidate in candidates:
        if candidate.is_file() and candidate.stat().st_size > 50_000_000:
            return candidate
    return None


def availability() -> tuple[bool, str]:
    """Return ``(available, detail)`` without loading the model."""

    try:
        hft._onnxruntime()
    except hft.TranscriptionUnavailable as exc:
        return False, str(exc)
    path = model_path()
    if path is None:
        return False, f"高精度模型未下载 · 约 {MODEL_SIZE_HINT} MB"
    return True, f"高精度 CRNN · {path.stat().st_size / 1e6:.0f} MB"


def download_model(
    *,
    progress: Callable[[int, int], None] | None = None,
    should_cancel: CancelFn | None = None,
) -> Path:
    """Download the CRNN model into the user data directory."""

    target = app_data_dir() / "models" / MODEL_NAME
    target.parent.mkdir(parents=True, exist_ok=True)
    partial = target.with_suffix(".onnx.part")
    last_error: Exception | None = None
    for url in MODEL_URLS:
        request = urllib.request.Request(url, headers={"User-Agent": "PianoWaterfall"})
        try:
            with urllib.request.urlopen(request, timeout=60) as response, partial.open("wb") as out:
                total = int(response.headers.get("Content-Length") or 0)
                done = 0
                while True:
                    if should_cancel is not None and should_cancel():
                        raise TranscriptionCancelled
                    chunk = response.read(512 * 1024)
                    if not chunk:
                        break
                    out.write(chunk)
                    done += len(chunk)
                    if progress is not None:
                        progress(done, total)
            partial.replace(target)
            return target
        except TranscriptionCancelled:
            partial.unlink(missing_ok=True)
            raise
        except Exception as exc:  # try the next mirror
            last_error = exc
            partial.unlink(missing_ok=True)
    raise RuntimeError(f"下载高精度模型失败：{last_error}")


# --------------------------------------------------------------------- decoding


def _local_peaks(values: np.ndarray, threshold: float) -> list[int]:
    """Indices of local maxima at least ``threshold``, ignoring plateaus."""

    if values.size < 5:
        return []
    core = values[2:-2]
    mask = (
        (core >= threshold)
        & (core >= values[1:-3])
        & (core > values[3:-1])
        & (core >= values[:-4])
        & (core > values[4:])
    )
    return (np.flatnonzero(mask) + 2).tolist()


def decode(
    onset: np.ndarray,
    offset: np.ndarray,
    frame: np.ndarray,
    velocity: np.ndarray,
) -> list[dict[str, float]]:
    """Decode note events from CRNN activations shaped ``(frames, 88)``."""

    frames = min(len(onset), len(offset), len(frame), len(velocity))
    notes: list[dict[str, float]] = []
    for pitch_index in range(NUM_NOTE):
        on = onset[:frames, pitch_index]
        off = offset[:frames, pitch_index]
        active = frame[:frames, pitch_index]
        strong = velocity[:frames, pitch_index]
        peaks = _local_peaks(on, ONSET_THRESHOLD)
        previous = -100
        for start in peaks:
            if start - previous < 4:  # 40 ms debounce
                continue
            previous = start
            end: int | None = None
            limit = min(frames - 3, start + int(4 * FRAMES_PER_SECOND))
            candidates = _local_peaks(off[start + 2 : limit], OFFSET_THRESHOLD)
            if candidates:
                end = start + 2 + candidates[0]
            if end is None:
                quiet = np.flatnonzero(active[start + 1 :] < FRAME_THRESHOLD)
                if quiet.size:
                    end = start + 1 + int(quiet[0])
            if end is None:
                end = frames
            if end <= start + 1:
                end = start + 2
            onset_seconds = start / FRAMES_PER_SECOND
            offset_seconds = end / FRAMES_PER_SECOND
            if offset_seconds - onset_seconds < MIN_DURATION:
                continue
            notes.append(
                {
                    "onset": onset_seconds,
                    "offset": offset_seconds,
                    "pitch": pitch_index + NOTE_MIN,
                    "velocity": max(1, min(127, int(round(strong[start] * 127)))),
                }
            )

    notes.sort(key=lambda note: (note["onset"], note["pitch"]))
    # A repeated note cannot start before the previous one was released.
    for previous, current in zip(notes, notes[1:], strict=False):
        if previous["pitch"] == current["pitch"] and previous["offset"] > current["onset"]:
            previous["offset"] = max(previous["onset"] + 0.02, current["onset"] - 0.01)
    return notes


# -------------------------------------------------------------------- inference


def transcribe(
    audio_path: str | Path,
    midi_path: str | Path,
    *,
    progress: ProgressFn | None = None,
    should_cancel: CancelFn | None = None,
) -> Path:
    """Transcribe a recording with the optional high-accuracy CRNN model."""

    audio_path = Path(audio_path)
    midi_path = Path(midi_path)
    if not audio_path.exists():
        raise FileNotFoundError(f"找不到音频文件：{audio_path}")
    path = model_path()
    if path is None:
        raise TranscriptionUnavailable(
            f"高精度转录模型尚未下载。请点击「下载高精度模型」（约 {MODEL_SIZE_HINT} MB）后再试。"
        )

    def report(fraction: float, message: str) -> None:
        if progress is not None:
            progress(fraction, message)
        if should_cancel is not None and should_cancel():
            raise TranscriptionCancelled

    report(0.01, "正在读取音频…")
    wave = hft.load_audio(audio_path)
    report(0.05, f"音频读取成功（{len(wave) / SAMPLE_RATE:.1f} 秒）")

    if len(wave) == 0:
        raise RuntimeError("音频文件为空，无法转录。")

    ort = hft._onnxruntime()
    options = ort.SessionOptions()
    options.intra_op_num_threads = max(1, min(8, os.cpu_count() or 4))
    # The exported CRNN hits a MatMul/BatchNorm fusion bug in ORT 1.20+.
    options.graph_optimization_level = ort.GraphOptimizationLevel.ORT_DISABLE_ALL
    session = ort.InferenceSession(
        str(path), sess_options=options, providers=["CPUExecutionProvider"]
    )

    starts = list(range(0, len(wave), HOP_SAMPLES))
    onset_parts: list[np.ndarray] = []
    offset_parts: list[np.ndarray] = []
    frame_parts: list[np.ndarray] = []
    velocity_parts: list[np.ndarray] = []
    for index, start in enumerate(starts):
        if should_cancel is not None and should_cancel():
            raise TranscriptionCancelled
        chunk = wave[start : start + SEGMENT_SAMPLES]
        take = NUM_FRAMES
        if start + SEGMENT_SAMPLES <= len(wave):
            take = 501  # 5 s, keeping a little margin at the segment edge
        else:
            take = min(NUM_FRAMES, int(np.ceil(len(chunk) / SAMPLE_RATE * FRAMES_PER_SECOND)))
        segment = np.zeros(SEGMENT_SAMPLES, dtype=np.float32)
        segment[: len(chunk)] = chunk
        outputs = session.run(None, {"audio": segment[None, :]})
        onset_parts.append(outputs[0][0, :take])
        offset_parts.append(outputs[1][0, :take])
        frame_parts.append(outputs[2][0, :take])
        velocity_parts.append(outputs[3][0, :take])
        report(
            0.05 + 0.88 * (index + 1) / len(starts),
            f"高精度转录中… {index + 1}/{len(starts)} 段",
        )

    onset = np.concatenate(onset_parts, axis=0)
    offset = np.concatenate(offset_parts, axis=0)
    frame = np.concatenate(frame_parts, axis=0)
    velocity = np.concatenate(velocity_parts, axis=0)
    report(0.94, "正在解码音符…")
    notes = decode(onset, offset, frame, velocity)
    duration = len(wave) / SAMPLE_RATE
    trimmed: list[dict[str, float]] = []
    for note in notes:
        if note["onset"] >= duration:
            continue
        note["offset"] = min(note["offset"], duration)
        if note["offset"] - note["onset"] >= MIN_DURATION:
            trimmed.append(note)
    notes = trimmed
    if not notes:
        raise RuntimeError("没有识别到音符，请确认音频中包含清晰的钢琴独奏。")
    report(0.97, f"识别到 {len(notes)} 个音符，正在写入 MIDI…")
    hft.write_midi(notes, midi_path)
    report(1.0, "转录完成")
    return midi_path
