"""Fetch and trim the bundled piano samples.

The samples come from the `tonejs-instruments` collection, whose piano
multisamples originate from Versilian Studios Chamber Orchestra 2 (Community
Edition).  They are released under CC-BY 3.0 – see
``src/piano_waterfall/assets/samples/ATTRIBUTION.md``.

Run this only when refreshing the bank; the trimmed WAV files are committed so
the app works offline and the release build stays reproducible.
"""

from __future__ import annotations

import argparse
import io
import sys
import urllib.request
import wave
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
DEST = ROOT / "src" / "piano_waterfall" / "assets" / "samples" / "piano"
BASE = "https://raw.githubusercontent.com/nbrosowsky/tonejs-instruments/master/samples/piano"
PITCH_NAMES = ("C", "Cs", "D", "Ds", "E", "F", "Fs", "G", "Gs", "A", "As", "B")
ROOTS = list(range(33, 109, 3))  # A1 .. C8, one sample every three semitones
MAX_SECONDS = 5.5
FADE_SECONDS = 0.35
TARGET_PEAK = 0.85


def sample_name(pitch: int) -> str:
    return f"{PITCH_NAMES[pitch % 12]}{pitch // 12 - 1}"


def read_wav(data: bytes) -> tuple[np.ndarray, int]:
    with wave.open(io.BytesIO(data), "rb") as handle:
        channels = handle.getnchannels()
        width = handle.getsampwidth()
        rate = handle.getframerate()
        frames = handle.readframes(handle.getnframes())
    if width != 2:
        raise ValueError(f"expected 16-bit samples, got {width * 8}-bit")
    audio = np.frombuffer(frames, dtype="<i2").astype(np.float32) / 32768.0
    if channels > 1:
        audio = audio.reshape(-1, channels).mean(axis=1)
    return audio, rate


def trim(audio: np.ndarray, rate: int) -> np.ndarray:
    # Drop the handful of silent samples before the hammer strike, and keep a
    # short pre-roll so the attack transient is never clipped.
    loud = np.flatnonzero(np.abs(audio) > 0.004)
    onset = int(loud[0]) if loud.size else 0
    start = max(0, onset - int(0.005 * rate))
    end = min(len(audio), start + int(MAX_SECONDS * rate))
    audio = audio[start:end].copy()

    fade_in = min(len(audio), int(0.002 * rate))
    if fade_in:
        audio[:fade_in] *= np.linspace(0.0, 1.0, fade_in, dtype=np.float32)
    fade_out = min(len(audio), int(FADE_SECONDS * rate))
    if fade_out:
        curve = np.linspace(1.0, 0.0, fade_out, dtype=np.float32) ** 1.7
        audio[-fade_out:] *= curve

    peak = float(np.max(np.abs(audio))) if audio.size else 0.0
    if peak > 1e-6:
        audio *= TARGET_PEAK / peak
    return audio


def write_wav(path: Path, audio: np.ndarray, rate: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    pcm = (np.clip(audio, -1.0, 1.0) * 32767.0).astype("<i2")
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(rate)
        handle.writeframes(pcm.tobytes())


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--force", action="store_true", help="re-download existing samples")
    args = parser.parse_args(argv)

    total = 0
    for pitch in ROOTS:
        name = sample_name(pitch)
        target = DEST / f"{name}.wav"
        if target.exists() and not args.force:
            total += target.stat().st_size
            print(f"skip {name} (exists)")
            continue
        url = f"{BASE}/{name}.wav"
        print(f"fetch {name} <- {url}")
        with urllib.request.urlopen(url, timeout=60) as response:  # noqa: S310
            payload = response.read()
        audio, rate = read_wav(payload)
        write_wav(target, trim(audio, rate), rate)
        total += target.stat().st_size
        print(f"  {len(audio) / rate:.2f}s -> {target.stat().st_size / 1024:.0f} KiB")

    print(f"done: {len(ROOTS)} samples, {total / 1024 / 1024:.1f} MiB")
    return 0


if __name__ == "__main__":
    sys.exit(main())
