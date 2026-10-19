"""A small, dependency-light piano synthesiser.

The goal is not concert realism – it is a pleasant, consistent sound that
works on every platform without downloading a SoundFont.  Notes are rendered
as a sum of slightly inharmonic partials with a hammer transient, a
pitch-dependent decay and a handful of early reflections taken from the
original recording.

Rendering a three minute song takes a few seconds on a laptop, so the app
renders to a cached WAV file once and then lets Qt play that file.
"""

from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from .midi_io import Song, midi_frequency

ProgressFn = Callable[[float, str], None]
CancelFn = Callable[[], bool]

DEFAULT_SAMPLE_RATE = 44_100

#: (delay in ms, gain, pan) – cheap early reflections, no network needed.
_EARLY_REFLECTIONS = (
    (17.0, 0.16, -0.55),
    (29.0, 0.12, 0.60),
    (43.0, 0.10, -0.25),
    (61.0, 0.08, 0.45),
    (83.0, 0.06, -0.40),
    (109.0, 0.05, 0.50),
)


@dataclass(frozen=True, slots=True)
class SynthSettings:
    sample_rate: int = DEFAULT_SAMPLE_RATE
    max_harmonics: int = 12
    brightness: float = 1.0
    reverb: float = 0.55
    tail: float = 1.4
    normalize: float = 0.88

    @property
    def channels(self) -> int:
        return 2


DEFAULT_SETTINGS = SynthSettings()


def render_song(
    song: Song,
    settings: SynthSettings = DEFAULT_SETTINGS,
    *,
    progress: ProgressFn | None = None,
    should_cancel: CancelFn | None = None,
) -> np.ndarray:
    """Render ``song`` to a stereo float32 array of shape ``(frames, 2)``."""

    sr = settings.sample_rate
    if not song.notes:
        return np.zeros((sr, 2), dtype=np.float32)

    total_frames = int((song.duration + settings.tail) * sr) + 1
    buffer = np.zeros((total_frames, 2), dtype=np.float32)

    notes = song.notes
    count = len(notes)
    report_every = max(1, count // 100)

    for index, note in enumerate(notes):
        if should_cancel is not None and should_cancel():
            raise RenderCancelled
        start = int(note.start * sr)
        if start >= total_frames:
            continue
        _add_note(buffer, note, sr, settings, total_frames)
        if progress is not None and index % report_every == 0:
            figure = 0.85 * index / count
            progress(figure, f"正在合成钢琴音频… {index}/{count}")

    if settings.reverb > 0:
        _apply_reflections(buffer, sr, settings.reverb)

    # Remove DC and normalise to a comfortable level.
    buffer -= buffer.mean(axis=0, keepdims=True)
    peak = float(np.max(np.abs(buffer)))
    if peak > 1e-9:
        buffer *= min(settings.normalize / peak, 8.0)
    np.clip(buffer, -1.0, 1.0, out=buffer)

    if progress is not None:
        progress(1.0, "音频合成完成")
    return buffer


class RenderCancelled(RuntimeError):
    """Raised inside :func:`render_song` when the caller cancels."""


def _add_note(
    buffer: np.ndarray,
    note,
    sr: int,
    settings: SynthSettings,
    total_frames: int,
) -> None:
    f0 = midi_frequency(note.pitch)
    duration = max(min(note.duration, 30.0), 0.02)
    release = 0.10
    frames = min(int((duration + release) * sr) + 1, total_frames - int(note.start * sr))
    if frames <= 16:
        return

    t = np.arange(frames, dtype=np.float32) / sr

    # Envelope: fast attack, pitch dependent exponential decay, soft release.
    attack = 1.0 - np.exp(-t / 0.0045)
    tau = float(np.clip(2.4 * (261.63 / f0) ** 0.38, 0.35, 7.0))
    body = np.exp(-t / tau)
    release_env = np.ones_like(t)
    after = t > duration
    if np.any(after):
        release_env[after] = np.exp(-(t[after] - duration) / 0.09)
    envelope = attack * body * release_env

    # Slightly inharmonic partials, fewer of them for high notes.
    nyquist = sr * 0.45
    max_partial = int(min(settings.max_harmonics, max(1, nyquist // f0)))
    wave = np.zeros(frames, dtype=np.float32)
    for harmonic in range(1, max_partial + 1):
        amp = (1.0 / harmonic**1.35) * settings.brightness
        # Higher partials die away faster, as on a real string.
        amp *= np.exp(-t * harmonic * 0.22)
        freq = f0 * harmonic * (1.0 + 0.00012 * harmonic * harmonic)
        phase = (note.pitch * 0.77 + harmonic * 1.31) % (2.0 * math.pi)
        wave += (amp * np.sin(2.0 * math.pi * freq * t + phase)).astype(np.float32)

    # Hammer noise: a very short filtered burst at the attack.
    rng = np.random.default_rng(note.pitch * 31 + int(note.start * 1000))
    burst_len = min(frames, int(0.018 * sr))
    noise = rng.standard_normal(burst_len).astype(np.float32)
    if burst_len > 8:
        kernel = np.ones(6, dtype=np.float32) / 6.0
        noise = np.convolve(noise, kernel, mode="same")
    hammer = np.zeros(frames, dtype=np.float32)
    hammer[:burst_len] = noise * np.linspace(0.35, 0.0, burst_len) ** 1.5

    velocity = (note.velocity / 127.0) ** 1.5
    gain = 0.32 * velocity
    signal = (wave * envelope + hammer * 0.55) * gain

    # Equal-power panning, gently spread by pitch.
    pan = float(np.clip((note.pitch - 62) / 50.0, -1.0, 1.0)) * 0.45
    angle = (pan + 1.0) * math.pi / 4.0
    left, right = math.cos(angle), math.sin(angle)

    start = int(note.start * sr)
    stop = start + frames
    buffer[start:stop, 0] += signal * left
    buffer[start:stop, 1] += signal * right


def _apply_reflections(buffer: np.ndarray, sr: int, amount: float) -> None:
    mono = buffer.mean(axis=1)
    for delay_ms, gain, pan in _EARLY_REFLECTIONS:
        delay = int(delay_ms * 0.001 * sr)
        if delay <= 0 or delay >= len(mono):
            continue
        reflected = mono[:-delay] * (gain * amount)
        angle = (pan + 1.0) * math.pi / 4.0
        buffer[delay:, 0] += reflected * math.cos(angle)
        buffer[delay:, 1] += reflected * math.sin(angle)
    # A tiny bit of stereo width from the dry signal.
    buffer[:, 0] *= 0.98
    buffer[:, 1] *= 1.02


def write_wav(path: str | Path, audio: np.ndarray, sample_rate: int) -> Path:
    import soundfile as sf

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    # ``format`` is explicit so temp files such as "song.wav.part" work too.
    sf.write(str(path), audio, sample_rate, subtype="PCM_16", format="WAV")
    return path
