"""hFT-Transformer piano transcription (ONNX, no PyTorch at runtime).

The model is the official ISMIR 2023 hFT-Transformer checkpoint from Sony,
exported to ONNX.  It is small (about 22 MB) and accurate, which lets the app
ship audio-to-MIDI out of the box instead of asking users to install PyTorch.
"""

from __future__ import annotations

import os
import urllib.request
from collections.abc import Callable
from pathlib import Path

import numpy as np

from .paths import app_data_dir, bundled_asset

ProgressFn = Callable[[float, str], None]
CancelFn = Callable[[], bool]

SAMPLE_RATE = 16_000
HOP_SAMPLE = 256
N_FFT = 2048
N_MELS = 256
NUM_FRAME = 128
MARGIN = 32
NOTE_MIN = 21
NOTE_MAX = 108
NUM_NOTE = 88
THRESHOLD = 0.5
MODEL_NAME = "hft_transformer.onnx"
MODEL_URL = (
    "https://raw.githubusercontent.com/Dream-Alan/piano-waterfall/main/"
    "src/piano_waterfall/assets/models/hft_transformer.onnx"
)
MODEL_ENV = "PIANO_WATERFALL_MODEL"


class TranscriptionUnavailable(RuntimeError):
    """The ONNX model or onnxruntime is missing."""


class TranscriptionCancelled(RuntimeError):
    """The user cancelled the transcription."""


def model_path() -> Path | None:
    """Return the bundled or user-installed model file, if present."""

    override = os.environ.get(MODEL_ENV)
    candidates = []
    if override:
        candidates.append(Path(override))
    bundled = bundled_asset(f"models/{MODEL_NAME}")
    if bundled is not None:
        candidates.append(bundled)
    candidates.append(app_data_dir() / "models" / MODEL_NAME)
    for candidate in candidates:
        if candidate.is_file() and candidate.stat().st_size > 1_000_000:
            return candidate
    return None


def _onnxruntime():
    try:
        import onnxruntime as ort
    except Exception as exc:  # pragma: no cover - broken install
        raise TranscriptionUnavailable(
            "缺少 onnxruntime，无法运行内置转录模型。\n"
            "请重新安装 Piano Waterfall，或运行：pip install onnxruntime"
        ) from exc
    return ort


def availability() -> tuple[bool, str]:
    """Return ``(available, detail)`` without loading the model itself."""

    try:
        _onnxruntime()
    except TranscriptionUnavailable as exc:
        return False, str(exc)
    path = model_path()
    if path is None:
        return False, "转录模型缺失，可点击「一键下载 AI 模型」重新获取。"
    return True, f"内置 hFT-Transformer · {path.stat().st_size / 1e6:.0f} MB"


def download_model(
    *,
    progress: Callable[[int, int], None] | None = None,
    should_cancel: CancelFn | None = None,
) -> Path:
    """Download the ONNX model into the user data directory (one-click repair)."""

    target = app_data_dir() / "models" / MODEL_NAME
    target.parent.mkdir(parents=True, exist_ok=True)
    partial = target.with_suffix(".onnx.part")
    request = urllib.request.Request(MODEL_URL, headers={"User-Agent": "PianoWaterfall"})
    try:
        with urllib.request.urlopen(request, timeout=60) as response, partial.open("wb") as out:
            total = int(response.headers.get("Content-Length") or 0)
            done = 0
            while True:
                if should_cancel is not None and should_cancel():
                    raise TranscriptionCancelled
                chunk = response.read(256 * 1024)
                if not chunk:
                    break
                out.write(chunk)
                done += len(chunk)
                if progress is not None:
                    progress(done, total)
        partial.replace(target)
    except Exception:
        partial.unlink(missing_ok=True)
        raise
    return target


# --------------------------------------------------------------------------- audio


def load_audio(path: str | Path) -> np.ndarray:
    """Decode any format supported by libsndfile (wav/flac/ogg/mp3) as mono."""

    import soundfile as sf

    try:
        wave, sr = sf.read(str(path), dtype="float32", always_2d=True)
    except Exception as exc:
        raise RuntimeError(
            f"音频解码失败：{Path(path).name}\n"
            "当前格式可能不被支持，请先转换成 WAV 或 FLAC 再试。\n"
            f"原始错误：{exc}"
        ) from exc
    wave = wave.mean(axis=1)
    if sr != SAMPLE_RATE:
        wave = _resample_fft(wave, SAMPLE_RATE / sr)
    return np.ascontiguousarray(wave, dtype=np.float32)


def _resample_fft(wave: np.ndarray, ratio: float) -> np.ndarray:
    """Band-limited FFT resampling; enough for 16 kHz transcription features."""

    new_length = max(1, int(round(len(wave) * ratio)))
    spectrum = np.fft.rfft(wave)
    keep = min(len(spectrum), new_length // 2 + 1)
    out = np.zeros(new_length // 2 + 1, dtype=np.complex64)
    out[:keep] = spectrum[:keep]
    return np.fft.irfft(out, new_length).astype(np.float32) * (new_length / len(wave))


def _hz_to_mel(freq: np.ndarray) -> np.ndarray:
    return 2595.0 * np.log10(1.0 + np.asarray(freq, dtype=np.float64) / 700.0)


def _mel_to_hz(mel: np.ndarray) -> np.ndarray:
    return 700.0 * (10.0 ** (np.asarray(mel, dtype=np.float64) / 2595.0) - 1.0)


def _mel_filterbank() -> np.ndarray:
    fft_freqs = np.linspace(0.0, SAMPLE_RATE / 2.0, N_FFT // 2 + 1)
    mel_points = np.linspace(_hz_to_mel(0.0), _hz_to_mel(SAMPLE_RATE / 2.0), N_MELS + 2)
    hz_points = _mel_to_hz(mel_points)
    weights = np.zeros((N_MELS, fft_freqs.size), dtype=np.float64)
    for i in range(N_MELS):
        left, center, right = hz_points[i], hz_points[i + 1], hz_points[i + 2]
        rising = (fft_freqs - left) / max(center - left, 1e-12)
        falling = (right - fft_freqs) / max(right - center, 1e-12)
        weights[i] = np.maximum(0.0, np.minimum(rising, falling))
    enorm = 2.0 / (hz_points[2:] - hz_points[:-2])
    return (weights * enorm[:, None]).astype(np.float32)


_FILTERBANK: np.ndarray | None = None


def mel_spectrogram(wave: np.ndarray) -> np.ndarray:
    """Log mel spectrogram matching torchaudio's defaults used for training."""

    global _FILTERBANK
    if _FILTERBANK is None:
        _FILTERBANK = _mel_filterbank()
    window = np.hanning(N_FFT + 1)[:-1].astype(np.float32)
    padded = np.pad(np.asarray(wave, dtype=np.float32), (N_FFT // 2, N_FFT // 2))
    frames = np.lib.stride_tricks.sliding_window_view(padded, N_FFT)[::HOP_SAMPLE]
    spectrum = np.fft.rfft(frames * window, n=N_FFT, axis=1)
    power = (np.abs(spectrum) ** 2).astype(np.float32)
    mel = power @ _FILTERBANK.T
    return np.log(mel + 1e-8).astype(np.float32)


# ----------------------------------------------------------------------- decoding


def _peaks(values: np.ndarray, threshold: float = THRESHOLD) -> list[tuple[int, float]]:
    """Local maxima with the sub-frame interpolation used by the authors."""

    n = len(values)
    found: list[tuple[int, float]] = []
    for i in np.flatnonzero(values >= threshold):
        i = int(i)
        if i > 0 and values[i] < values[i - 1]:
            continue
        if i + 1 < n and values[i] < values[i + 1]:
            continue
        if i == 0 or i == n - 1 or values[i - 1] == values[i + 1]:
            time = i * HOP_SAMPLE / SAMPLE_RATE
        elif values[i - 1] > values[i + 1]:
            denom = float(values[i] - values[i + 1])
            time = i * HOP_SAMPLE / SAMPLE_RATE - (HOP_SAMPLE / SAMPLE_RATE) * 0.5 * float(
                values[i - 1] - values[i + 1]
            ) / max(denom, 1e-9)
        else:
            denom = float(values[i] - values[i - 1])
            time = i * HOP_SAMPLE / SAMPLE_RATE + (HOP_SAMPLE / SAMPLE_RATE) * 0.5 * float(
                values[i + 1] - values[i - 1]
            ) / max(denom, 1e-9)
        found.append((i, time))
    return found


def decode_notes(
    onset: np.ndarray,
    offset: np.ndarray,
    mpe: np.ndarray,
    velocity: np.ndarray,
    *,
    threshold: float = THRESHOLD,
) -> list[dict[str, float]]:
    """Convert per-frame onset/offset/MPE probabilities into note events."""

    hop_sec = HOP_SAMPLE / SAMPLE_RATE
    notes: list[dict[str, float]] = []
    for pitch_index in range(NUM_NOTE):
        onset_peaks = _peaks(onset[:, pitch_index], threshold)
        offset_peaks = _peaks(offset[:, pitch_index], threshold)
        offset_locs = np.array([item[0] for item in offset_peaks], dtype=int)
        offset_times = np.array([item[1] for item in offset_peaks], dtype=float)
        for index, (loc, start) in enumerate(onset_peaks):
            next_loc = onset_peaks[index + 1][0] if index + 1 < len(onset_peaks) else len(mpe)
            next_time = (
                onset_peaks[index + 1][1]
                if index + 1 < len(onset_peaks)
                else (len(mpe) - 1) * hop_sec
            )
            pos = np.searchsorted(offset_locs, loc, side="right")
            has_offset = pos < len(offset_locs)
            offset_loc = int(offset_locs[pos]) if has_offset else loc + 1
            offset_time = float(offset_times[pos]) if has_offset else 0.0
            if offset_loc > next_loc:
                offset_loc, offset_time = next_loc, next_time
            mpe_loc = loc + 1
            has_mpe = False
            mpe_time = 0.0
            below = np.flatnonzero(mpe[loc + 1 : next_loc, pitch_index] < threshold)
            if len(below):
                mpe_loc = int(below[0]) + loc + 1
                has_mpe = True
                mpe_time = mpe_loc * hop_sec
            if not has_offset and not has_mpe:
                end = next_time
            elif has_offset and not has_mpe:
                end = offset_time
            elif not has_offset and has_mpe:
                end = mpe_time
            else:
                end = offset_time if offset_loc <= mpe_loc else mpe_time
            value = int(velocity[loc, pitch_index])
            if value <= 0 or end <= start:
                continue
            notes.append(
                {
                    "pitch": pitch_index + NOTE_MIN,
                    "onset": float(start),
                    "offset": float(end),
                    "velocity": value,
                }
            )
            if (
                len(notes) > 1
                and notes[-1]["pitch"] == notes[-2]["pitch"]
                and notes[-1]["onset"] < notes[-2]["offset"]
            ):
                notes[-2]["offset"] = notes[-1]["onset"]
    notes.sort(key=lambda note: (note["onset"], note["pitch"]))
    return notes


def write_midi(notes: list[dict[str, float]], path: str | Path) -> Path:
    import mido

    path = Path(path)
    ticks_per_beat = 960
    tempo = 500_000  # 120 BPM
    midi = mido.MidiFile(ticks_per_beat=ticks_per_beat)
    track = mido.MidiTrack()
    midi.tracks.append(track)
    track.append(mido.MetaMessage("set_tempo", tempo=tempo, time=0))

    def ticks(seconds: float) -> int:
        return int(round(seconds * ticks_per_beat * 1_000_000 / tempo))

    events: list[tuple[int, int, int, int]] = []
    for note in notes:
        start = ticks(note["onset"])
        end = max(start + 1, ticks(note["offset"]))
        pitch = int(note["pitch"])
        velocity = max(1, min(127, int(note["velocity"])))
        events.append((start, 1, pitch, velocity))
        events.append((end, 0, pitch, 0))
    events.sort(key=lambda item: (item[0], item[1], item[2]))
    last = 0
    for tick, is_on, pitch, velocity in events:
        delta = max(0, tick - last)
        last = tick
        track.append(
            mido.Message(
                "note_on" if is_on else "note_off",
                note=pitch,
                velocity=velocity,
                time=delta,
            )
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    midi.save(path)
    return path


# -------------------------------------------------------------------- inference


def transcribe(
    audio_path: str | Path,
    midi_path: str | Path,
    *,
    progress: ProgressFn | None = None,
    should_cancel: CancelFn | None = None,
) -> Path:
    """Transcribe a piano recording to MIDI with the bundled ONNX model."""

    audio_path = Path(audio_path)
    midi_path = Path(midi_path)
    if not audio_path.exists():
        raise FileNotFoundError(f"找不到音频文件：{audio_path}")
    path = model_path()
    if path is None:
        raise TranscriptionUnavailable(
            "转录模型缺失。请点击「一键下载 AI 模型」重新获取（约 22 MB）。"
        )

    def report(fraction: float, message: str) -> None:
        if progress is not None:
            progress(fraction, message)
        if should_cancel is not None and should_cancel():
            raise TranscriptionCancelled

    report(0.02, "正在读取音频…")
    wave = load_audio(audio_path)
    report(0.10, f"音频读取成功（{len(wave) / SAMPLE_RATE:.1f} 秒）")
    feature = mel_spectrogram(wave)
    report(0.16, "正在运行 hFT-Transformer…")

    ort = _onnxruntime()
    options = ort.SessionOptions()
    options.intra_op_num_threads = max(1, min(8, os.cpu_count() or 4))
    options.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
    session = ort.InferenceSession(
        str(path), sess_options=options, providers=["CPUExecutionProvider"]
    )

    total = int(np.ceil(len(feature) / NUM_FRAME) * NUM_FRAME)
    padded = np.pad(feature, ((MARGIN, MARGIN), (0, 0)), constant_values=-18.0)
    padded = np.pad(padded, ((0, total - len(feature)), (0, 0)), constant_values=-18.0)

    onset = np.zeros((total, NUM_NOTE), np.float32)
    offset = np.zeros_like(onset)
    mpe = np.zeros_like(onset)
    velocity = np.zeros((total, NUM_NOTE), np.int8)
    windows = max(1, int(np.ceil(len(feature) / NUM_FRAME)))
    for index, start in enumerate(range(0, len(feature), NUM_FRAME)):
        if should_cancel is not None and should_cancel():
            raise TranscriptionCancelled
        window = padded[start : start + NUM_FRAME + 2 * MARGIN].T[None]
        out = session.run(None, {"spec": window})
        onset[start : start + NUM_FRAME] = out[0][0]
        offset[start : start + NUM_FRAME] = out[1][0]
        mpe[start : start + NUM_FRAME] = out[2][0]
        velocity[start : start + NUM_FRAME] = out[3][0].argmax(axis=2)
        report(0.16 + 0.76 * (index + 1) / windows, f"正在转录… {index + 1}/{windows}")

    notes = decode_notes(onset, offset, mpe, velocity)
    if not notes:
        raise RuntimeError("没有识别到音符，请确认音频中包含清晰的钢琴独奏。")
    report(0.96, f"识别到 {len(notes)} 个音符，正在写入 MIDI…")
    write_midi(notes, midi_path)
    report(1.0, "转录完成")
    return midi_path
