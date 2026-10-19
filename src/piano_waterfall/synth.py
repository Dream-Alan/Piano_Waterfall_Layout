"""A small, dependency-light piano synthesiser with several voices.

The goal is not concert realism – it is a pleasant, consistent sound that
works on every platform without downloading a SoundFont.  Notes are rendered
as a sum of slightly inharmonic partials with a hammer transient, a
pitch-dependent decay and a handful of early reflections.

Five voices are included so the same MIDI file can sound like a concert grand,
a bright pop piano, a felt piano, an old upright or an electric piano.  The
voice is part of the render cache key, so switching back to a previous voice
is instant.

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
DEFAULT_VOICE = "grand"

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
class Voice:
    """Parameters that give a rendered note its character."""

    key: str
    name: str
    description: str
    partials: int = 12
    tilt: float = 1.30
    brightness: float = 1.0
    attack: float = 0.004
    decay: float = 2.80
    partial_decay: float = 0.20
    inharmonicity: float = 0.00018
    detune_cents: float = 0.6
    hammer: float = 0.45
    hammer_tone: float = 0.45
    release: float = 0.10
    reverb: float = 0.55
    stereo: float = 0.45
    gain: float = 0.30


VOICES: dict[str, Voice] = {
    "grand": Voice(
        key="grand",
        name="音乐会三角",
        description="均衡、温暖，适合古典与流行",
        partials=14,
        tilt=1.30,
        brightness=1.00,
        attack=0.0040,
        decay=2.90,
        partial_decay=0.18,
        inharmonicity=0.00018,
        detune_cents=0.7,
        hammer=0.45,
        hammer_tone=0.45,
        release=0.10,
        reverb=0.55,
        stereo=0.45,
    ),
    "bright": Voice(
        key="bright",
        name="明亮流行",
        description="通透、颗粒感强，适合流行与摇滚",
        partials=16,
        tilt=1.10,
        brightness=1.35,
        attack=0.0025,
        decay=2.20,
        partial_decay=0.16,
        inharmonicity=0.00012,
        detune_cents=0.5,
        hammer=0.65,
        hammer_tone=0.75,
        release=0.08,
        reverb=0.42,
        stereo=0.50,
    ),
    "felt": Voice(
        key="felt",
        name="毛毡柔音",
        description="柔和、朦胧，像琴槌上盖了一层毛毡",
        partials=9,
        tilt=1.65,
        brightness=0.55,
        attack=0.0120,
        decay=3.40,
        partial_decay=0.25,
        inharmonicity=0.00025,
        detune_cents=1.2,
        hammer=0.18,
        hammer_tone=0.15,
        release=0.14,
        reverb=0.48,
        stereo=0.35,
    ),
    "upright": Voice(
        key="upright",
        name="复古立式",
        description="略带走音的旧立式钢琴，温暖有颗粒",
        partials=12,
        tilt=1.28,
        brightness=1.12,
        attack=0.0030,
        decay=2.10,
        partial_decay=0.24,
        inharmonicity=0.00050,
        detune_cents=4.0,
        hammer=0.55,
        hammer_tone=0.55,
        release=0.07,
        reverb=0.32,
        stereo=0.30,
    ),
    "electric": Voice(
        key="electric",
        name="梦幻电钢",
        description="钟声般的电钢琴，适合氛围与慢曲",
        partials=7,
        tilt=0.95,
        brightness=0.70,
        attack=0.0060,
        decay=1.70,
        partial_decay=0.55,
        inharmonicity=0.00005,
        detune_cents=0.0,
        hammer=0.08,
        hammer_tone=0.50,
        release=0.12,
        reverb=0.62,
        stereo=0.55,
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
            figure = 0.85 * index / count
            progress(figure, f"正在合成钢琴音频… {index}/{count}")

    if settings.reverb > 0:
        amount = min(1.0, settings.reverb * (voice.reverb / 0.55))
        _apply_reflections(buffer, sr, amount)

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
    f0 = midi_frequency(note.pitch)
    duration = max(min(note.duration, 30.0), 0.02)
    start = int(note.start * sr)
    frames = min(int((duration + voice.release) * sr) + 1, total_frames - start)
    if frames <= 16:
        return

    t = np.arange(frames, dtype=np.float32) / sr
    velocity = (note.velocity / 127.0) ** 1.6

    # Attack is a few milliseconds; felt is deliberately softer.
    attack = 1.0 - np.exp(-t / max(voice.attack, 0.0008))
    tau = float(np.clip(voice.decay * (261.63 / f0) ** 0.42, 0.30, 12.0))

    # Release when the key is lifted (MIDI sustain is already baked into duration).
    release_env = np.ones_like(t)
    after = t > duration
    if np.any(after):
        release_env[after] = np.exp(-(t[after] - duration) / max(voice.release * 0.9, 0.02))
    envelope = attack * release_env

    nyquist = sr * 0.46
    max_partial = int(
        min(settings.max_harmonics, voice.partials, max(1, int(nyquist / max(f0, 1.0))))
    )
    if max_partial < 1:
        return

    # Inharmonic strings are stiffer in the bass.
    inharm = voice.inharmonicity * (1.0 + max(0.0, 60.0 - note.pitch) / 55.0)
    indices = np.arange(1, max_partial + 1, dtype=np.float32)
    weights = indices ** (-voice.tilt)
    weights *= 1.0 + 0.35 * (indices / max_partial) * velocity
    weights /= float(weights.sum())

    brightness = voice.brightness * settings.brightness * (0.55 + 0.45 * velocity)
    wave_l = np.zeros(frames, dtype=np.float32)
    wave_r = np.zeros(frames, dtype=np.float32)

    for n in range(1, max_partial + 1):
        freq = f0 * n * math.sqrt(1.0 + inharm * n * n)
        if freq >= nyquist:
            break
        # High partials die away faster than the fundamental.
        tau_n = tau / (1.0 + (n - 1) * voice.partial_decay)
        amp = (float(weights[n - 1]) * brightness * np.exp(-t / tau_n) * envelope).astype(
            np.float32
        )
        phase = (note.pitch * 0.73 + n * 1.37) % (2.0 * math.pi)
        omega = 2.0 * math.pi * freq

        # The first few partials use a detuned second string for unison width.
        if n <= 4 and voice.detune_cents > 0.05:
            ratio = 2.0 ** (voice.detune_cents * (1.0 + 0.30 * (n - 1)) / 1200.0)
            wave_l += amp * np.sin(omega * t + phase)
            wave_r += amp * np.sin(omega * ratio * t + phase + 1.7)
        else:
            osc = np.sin(omega * t + phase)
            wave_l += amp * osc
            wave_r += amp * osc

    # Hammer noise: short, bright for pop pianos, dull for felt.
    seed = note.pitch * 31 + start + sum(ord(char) for char in voice.key)
    rng = np.random.default_rng(seed)
    burst = min(frames, max(8, int((0.010 + 0.018 * (1.0 - voice.hammer_tone)) * sr)))
    noise = rng.standard_normal(burst).astype(np.float32)
    if voice.hammer_tone >= 0.5:
        noise = np.diff(noise, prepend=np.float32(0.0))
    else:
        kernel = np.ones(8, dtype=np.float32) / 8.0
        noise = np.convolve(noise, kernel, mode="same")
    hammer_env = np.exp(
        -np.arange(burst, dtype=np.float32) / (sr * (0.0025 + 0.004 * voice.hammer_tone))
    )
    hammer = noise * hammer_env * voice.hammer * (0.25 + 0.75 * velocity) * brightness

    gain = voice.gain
    signal_l = wave_l * gain
    signal_r = wave_r * gain
    signal_l[:burst] += hammer * gain
    signal_r[:burst] += hammer * gain

    # Equal-power panning, gently spread by pitch.
    pan = float(np.clip((note.pitch - 62) / 50.0, -1.0, 1.0)) * voice.stereo
    angle = (pan + 1.0) * math.pi / 4.0
    left, right = math.cos(angle), math.sin(angle)

    stop = start + frames
    buffer[start:stop, 0] += signal_l * left
    buffer[start:stop, 1] += signal_r * right


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
