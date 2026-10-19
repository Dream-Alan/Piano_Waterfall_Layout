"""Sampled piano renderer with five character presets.

Notes are played back from a small bundled sample bank (one recording every
three semitones) and shifted with band-limited resampling.  Each voice applies
a different tone shaping (filter + shelf), release and ambience, so the presets
sound clearly different while still being a real piano.

Rendering a three minute song takes a few seconds, so the app caches the WAV
once and lets Qt play that file.  The standard-library ``wave`` writer keeps
the frozen build free of libsndfile/ctypes.
"""

from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from .midi_io import Song
from .samples import sample_for

ProgressFn = Callable[[float, str], None]
CancelFn = Callable[[], bool]

DEFAULT_SAMPLE_RATE = 44_100
DEFAULT_VOICE = "grand"

#: (delay in ms, gain, pan) – cheap early reflections, no network needed.
_EARLY_REFLECTIONS = (
    (17.0, 0.13, -0.55),
    (29.0, 0.10, 0.60),
    (43.0, 0.08, -0.25),
    (61.0, 0.07, 0.45),
    (83.0, 0.05, -0.40),
    (109.0, 0.04, 0.50),
)


@dataclass(frozen=True, slots=True)
class Voice:
    """Tone-shaping parameters applied on top of the sampled piano."""

    key: str
    name: str
    description: str
    lowpass_hz: float | None = None
    high_shelf_db: float = 0.0
    low_shelf_db: float = 0.0
    presence_db: float = 0.0
    attack: float = 0.0015
    release: float = 0.14
    reverb: float = 0.55
    stereo: float = 0.45
    gain: float = 0.34
    delay_ms: float = 0.0
    delay_mix: float = 0.0
    drive: float = 1.0


VOICES: dict[str, Voice] = {
    "grand": Voice(
        key="grand",
        name="音乐会三角",
        description="真实三角钢琴采样，均衡自然，适合古典与流行",
        high_shelf_db=0.0,
        release=0.16,
        reverb=0.50,
        stereo=0.45,
        gain=0.34,
    ),
    "bright": Voice(
        key="bright",
        name="明亮流行",
        description="大幅提亮高频、收紧低频，颗粒清晰，适合流行与摇滚",
        high_shelf_db=10.0,
        low_shelf_db=-3.0,
        presence_db=4.0,
        release=0.08,
        reverb=0.16,
        stereo=0.50,
        drive=1.35,
        gain=0.40,
    ),
    "felt": Voice(
        key="felt",
        name="毛毡柔音",
        description="重低通与柔和起音，像琴槌上盖了一层毛毡",
        lowpass_hz=1000.0,
        high_shelf_db=-9.0,
        attack=0.020,
        release=0.22,
        reverb=0.36,
        stereo=0.28,
        gain=0.44,
    ),
    "upright": Voice(
        key="upright",
        name="复古立式",
        description="窄频响、短延迟与木箱共鸣，旧立式钢琴的味道",
        lowpass_hz=4200.0,
        high_shelf_db=-4.0,
        low_shelf_db=3.5,
        attack=0.002,
        release=0.10,
        reverb=0.22,
        stereo=0.26,
        gain=0.42,
        delay_ms=18.0,
        delay_mix=0.28,
    ),
    "room": Voice(
        key="room",
        name="近场录音",
        description="近距离、干爽的录音棚音色，低频饱满、几乎无混响",
        low_shelf_db=5.0,
        high_shelf_db=-4.5,
        attack=0.0012,
        release=0.12,
        reverb=0.08,
        stereo=0.24,
        gain=0.40,
    ),
}


def voice_choices() -> list[Voice]:
    """Voices in display order (used by the UI and README)."""

    return list(VOICES.values())


def get_voice(key: str | None) -> Voice:
    return VOICES.get(key or "", VOICES[DEFAULT_VOICE])


@dataclass(frozen=True, slots=True)
class SynthSettings:
    sample_rate: int = DEFAULT_SAMPLE_RATE
    max_harmonics: int = 16
    brightness: float = 1.0
    reverb: float = 0.55
    tail: float = 1.4
    normalize: float = 0.88
    voice: str = DEFAULT_VOICE

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
    voice = get_voice(settings.voice)

    notes = song.notes
    count = len(notes)
    report_every = max(1, count // 100)

    for index, note in enumerate(notes):
        if should_cancel is not None and should_cancel():
            raise RenderCancelled
        start = int(note.start * sr)
        if start >= total_frames:
            continue
        _add_note(buffer, note, sr, settings, total_frames, voice)
        if progress is not None and index % report_every == 0:
            figure = 0.80 * index / count
            progress(figure, f"正在渲染钢琴音频… {index}/{count}")

    if progress is not None:
        progress(0.84, "正在塑造音色…")
    _apply_voice_color(buffer, sr, voice)

    if settings.reverb > 0:
        amount = min(1.0, settings.reverb * (voice.reverb / 0.50))
        _apply_reflections(buffer, sr, amount)
    if voice.delay_ms > 0 and voice.delay_mix > 0:
        _apply_slap_delay(buffer, sr, voice.delay_ms, voice.delay_mix)
    if voice.drive > 1.01:
        buffer = np.tanh(buffer * voice.drive) / math.tanh(voice.drive)

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
    voice: Voice | None = None,
) -> None:
    voice = voice or get_voice(settings.voice)
    sample = sample_for(note.pitch, sr)
    if sample.size < 8:
        return

    start = int(note.start * sr)
    duration = max(min(note.duration, 30.0), 0.02)
    frames = min(int((duration + voice.release) * sr) + 1, total_frames - start, sample.size)
    if frames <= 16:
        return

    t = np.arange(frames, dtype=np.float32) / sr
    velocity = (note.velocity / 127.0) ** 1.35

    # Keep the recorded attack; felt starts noticeably softer.
    envelope = 1.0 - np.exp(-t / max(voice.attack, 0.0005))
    after = t > duration
    if np.any(after):
        envelope[after] *= np.exp(-(t[after] - duration) / max(voice.release, 0.02))

    signal = sample[:frames] * envelope * (velocity * voice.gain)
    pan = float(np.clip((note.pitch - 62) / 50.0, -1.0, 1.0)) * voice.stereo
    angle = (pan + 1.0) * math.pi / 4.0
    left, right = math.cos(angle), math.sin(angle)

    stop = start + frames
    buffer[start:stop, 0] += signal * left
    buffer[start:stop, 1] += signal * right


def _shape_curve(freqs: np.ndarray, voice: Voice) -> np.ndarray:
    """Frequency response (linear gain) for a voice."""

    gain = np.ones_like(freqs)
    if voice.lowpass_hz:
        ratio = freqs / max(voice.lowpass_hz, 20.0)
        gain *= 1.0 / (1.0 + ratio**4)
    if voice.high_shelf_db:
        shelf = freqs**2 / (freqs**2 + 2500.0**2)
        gain *= 10.0 ** (voice.high_shelf_db * shelf / 20.0)
    if voice.low_shelf_db:
        shelf = 250.0**2 / (freqs**2 + 250.0**2)
        gain *= 10.0 ** (voice.low_shelf_db * shelf / 20.0)
    if voice.presence_db:
        octaves = np.log2(np.maximum(freqs, 1.0) / 3200.0)
        bump = np.exp(-0.5 * (octaves / 0.9) ** 2)
        gain *= 10.0 ** (voice.presence_db * bump / 20.0)
    return gain


def _apply_voice_color(buffer: np.ndarray, sr: int, voice: Voice) -> None:
    if (
        voice.lowpass_hz is None
        and not voice.high_shelf_db
        and not voice.low_shelf_db
        and not voice.presence_db
    ):
        return
    frames = buffer.shape[0]
    freqs = np.fft.rfftfreq(frames, 1.0 / sr)
    curve = _shape_curve(freqs, voice).astype(np.float64)
    for channel in range(buffer.shape[1]):
        spectrum = np.fft.rfft(buffer[:, channel])
        spectrum *= curve
        buffer[:, channel] = np.fft.irfft(spectrum, n=frames).astype(np.float32)


def _apply_slap_delay(buffer: np.ndarray, sr: int, delay_ms: float, mix: float) -> None:
    delay = int(delay_ms * 0.001 * sr)
    if delay <= 0 or delay >= buffer.shape[0]:
        return
    delayed = np.zeros_like(buffer)
    delayed[delay:] = buffer[:-delay]
    buffer += delayed * mix


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
    buffer[:, 0] *= 0.99
    buffer[:, 1] *= 1.01


def write_wav(path: str | Path, audio: np.ndarray, sample_rate: int) -> Path:
    """Write 16-bit stereo PCM without third-party audio libraries.

    The standard-library ``wave`` writer keeps the frozen Windows build free of
    libsndfile/ctypes, which PyInstaller does not always collect correctly.
    """

    import wave

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    data = np.asarray(audio, dtype=np.float32)
    if data.ndim == 1:
        data = np.column_stack([data, data])
    elif data.shape[1] == 1:
        data = np.repeat(data, 2, axis=1)
    pcm = (np.clip(data[:, :2], -1.0, 1.0) * 32767.0).astype("<i2")

    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(2)
        handle.setsampwidth(2)
        handle.setframerate(int(sample_rate))
        handle.writeframes(pcm.tobytes())
    return path
