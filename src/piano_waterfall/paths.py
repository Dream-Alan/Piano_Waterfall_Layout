"""Application paths and a small on-disk cache for rendered audio."""

from __future__ import annotations

import hashlib
import json
import os
import sys
import tempfile
from pathlib import Path

from .synth import SynthSettings

APP_NAME = "PianoWaterfall"
CACHE_VERSION = 4
DATA_DIR_ENV = "PIANO_WATERFALL_DATA_DIR"


def app_data_dir() -> Path:
    """Per-user directory for caches, generated MIDI files and settings.

    Set ``PIANO_WATERFALL_DATA_DIR`` for a portable install, tests or CI.
    Falls back to the system temp directory if the preferred location is
    not writable (locked-down machines, sandboxes).
    """

    override = os.environ.get(DATA_DIR_ENV)
    if override:
        path = Path(override).expanduser()
    elif sys.platform == "win32":
        base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
        path = base / APP_NAME
    elif sys.platform == "darwin":
        path = Path.home() / "Library" / "Application Support" / APP_NAME
    else:
        base = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))
        path = base / APP_NAME

    for candidate in _data_dir_candidates(path):
        try:
            candidate.mkdir(parents=True, exist_ok=True)
            return candidate
        except OSError:
            continue
    raise OSError(f"no writable data directory found (tried {path})")


def _data_dir_candidates(preferred: Path) -> list[Path]:
    candidates = [preferred]
    try:
        temp_root = Path(tempfile.gettempdir())
        if temp_root.resolve() != Path.cwd().resolve():
            candidates.append(temp_root / APP_NAME)
    except OSError:
        pass
    candidates.append(Path.cwd() / ".piano-waterfall-data")
    return candidates


def audio_cache_dir() -> Path:
    path = app_data_dir() / "audio-cache"
    path.mkdir(parents=True, exist_ok=True)
    return path


def transcriptions_dir() -> Path:
    path = app_data_dir() / "transcriptions"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _fingerprint(path: Path, settings: SynthSettings) -> str:
    stat = path.stat()
    payload = {
        "version": CACHE_VERSION,
        "path": str(path.resolve()),
        "size": stat.st_size,
        "mtime": stat.st_mtime_ns,
        "sr": settings.sample_rate,
        "harmonics": settings.max_harmonics,
        "brightness": settings.brightness,
        "reverb": settings.reverb,
        "tail": settings.tail,
        "voice": settings.voice,
    }
    return hashlib.sha1(json.dumps(payload, sort_keys=True).encode()).hexdigest()[:20]


def cached_audio_path(midi_path: str | Path, settings: SynthSettings) -> Path:
    midi_path = Path(midi_path)
    try:
        digest = _fingerprint(midi_path, settings)
    except OSError:
        digest = hashlib.sha1(str(midi_path).encode()).hexdigest()[:20]
    return audio_cache_dir() / f"{midi_path.stem}-{digest}.wav"


def bundled_asset(name: str) -> Path | None:
    """Locate an asset both in a source checkout and in a PyInstaller build."""

    here = Path(__file__).resolve().parent
    candidates = [
        here / "assets" / name,
        here.parent.parent / "assets" / name,
    ]
    bundle = getattr(sys, "_MEIPASS", None)
    if bundle:
        candidates.insert(0, Path(bundle) / "assets" / name)
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return None
