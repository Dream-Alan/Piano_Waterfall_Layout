"""Load the bundled, trimmed piano samples.

The bank contains one recording every three semitones (A1 … C8).  Notes in
between are produced by band-limited resampling, which keeps the attack and
decay of a real piano instead of stacking sine waves.

Samples: ``tonejs-instruments`` (piano: VSCO 2 Community Edition), CC-BY 3.0.
See ``assets/samples/ATTRIBUTION.md`` next to the WAV files.
"""

from __future__ import annotations

import os
import sys
import wave
from functools import lru_cache
from pathlib import Path

import numpy as np

SAMPLES_ENV = "PIANO_WATERFALL_SAMPLES"
PITCH_NAMES = ("C", "Cs", "D", "Ds", "E", "F", "Fs", "G", "Gs", "A", "As", "B")


class SampleBankMissing(RuntimeError):
    """Raised when the bundled piano samples cannot be found."""


def note_name(pitch: int) -> str:
    return f"{PITCH_NAMES[pitch % 12]}{pitch // 12 - 1}"


def _candidate_dirs() -> list[Path]:
    override = os.environ.get(SAMPLES_ENV)
    if override:
        return [Path(override).expanduser()]
    here = Path(__file__).resolve().parent
    candidates = [here / "assets" / "samples" / "piano"]
    bundle = getattr(sys, "_MEIPASS", None)
    if bundle:
        candidates.append(Path(bundle) / "assets" / "samples" / "piano")
    return candidates


def samples_dir() -> Path:
    for candidate in _candidate_dirs():
        if candidate.is_dir() and any(candidate.glob("*.wav")):
            return candidate
    locations = ", ".join(str(path) for path in _candidate_dirs())
    raise SampleBankMissing(f"Piano samples not found (looked in: {locations})")


def _read_wav(path: Path) -> tuple[np.ndarray, int]:
    with wave.open(str(path), "rb") as handle:
        channels = handle.getnchannels()
        width = handle.getsampwidth()
        rate = handle.getframerate()
        raw = handle.readframes(handle.getnframes())
    if width != 2:
        raise SampleBankMissing(f"{path.name}: expected 16-bit PCM")
    audio = np.frombuffer(raw, dtype="<i2").astype(np.float32) / 32768.0
    if channels > 1:
        audio = audio.reshape(-1, channels).mean(axis=1)
    return audio, rate


def _parse_pitch(name: str) -> int | None:
    stem = name.removesuffix(".wav")
    if not stem:
        return None
    for index, prefix in enumerate(PITCH_NAMES):
        if stem.startswith(prefix):
            tail = stem[len(prefix) :]
            if tail.lstrip("-").isdigit():
                octave = int(tail)
                return (octave + 1) * 12 + index
    return None


@lru_cache(maxsize=1)
def bank() -> tuple[dict[int, Path], tuple[int, ...]]:
    """Map root pitch → WAV path plus the sorted root list."""

    directory = samples_dir()
    mapping: dict[int, Path] = {}
    for path in directory.glob("*.wav"):
        pitch = _parse_pitch(path.name)
        if pitch is not None:
            mapping[pitch] = path
    if not mapping:
        raise SampleBankMissing(f"No usable WAV files in {directory}")
    roots = tuple(sorted(mapping))
    return mapping, roots


@lru_cache(maxsize=128)
def sample_for(pitch: int, sample_rate: int) -> np.ndarray:
    """Return a mono float32 sample for ``pitch``, resampled to ``sample_rate``."""

    mapping, roots = bank()
    closest = min(roots, key=lambda root: abs(root - pitch))
    audio, rate = _read_wav(mapping[closest])
    if rate != sample_rate:
        audio = _resample(audio, rate / sample_rate)
    semitones = pitch - closest
    if semitones:
        audio = _resample(audio, 2.0 ** (-semitones / 12.0))
    return audio


def _resample(audio: np.ndarray, ratio: float) -> np.ndarray:
    """Band-limited resampling through the FFT.

    ``ratio`` is the output/input length ratio: <1 shortens the sample and
    raises its pitch, >1 lengthens it and lowers the pitch.
    """

    if audio.size < 8 or abs(ratio - 1.0) < 1e-6:
        return audio
    target = max(32, int(round(audio.size * ratio)))
    if target == audio.size:
        return audio
    spectrum = np.fft.rfft(audio)
    if target <= audio.size:
        keep = target // 2 + 1
        spectrum = spectrum[:keep]
    else:
        padded = np.zeros(target // 2 + 1, dtype=np.complex128)
        padded[: spectrum.size] = spectrum
        spectrum = padded
    result = np.fft.irfft(spectrum, n=target).astype(np.float32)
    result *= target / audio.size
    fade = min(64, result.size // 8)
    if fade:
        ramp = np.linspace(0.0, 1.0, fade, dtype=np.float32)
        result[:fade] *= ramp
        result[-fade:] *= ramp[::-1]
    return result


def clear_cache() -> None:
    """Drop loaded samples (used by tests and after changing the bank)."""

    sample_for.cache_clear()
    bank.cache_clear()
