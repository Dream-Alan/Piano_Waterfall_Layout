# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller recipe for a self-contained Windows build (onedir)."""

from pathlib import Path

import PySide6

ROOT = Path(SPECPATH).resolve().parent
ICON = ROOT / "assets" / "icon.ico"

# Qt 6.12 ships its multimedia backend as FFmpeg DLLs; PyInstaller's hook does
# not always pick up swresample/swscale, which WAV decoding needs.
qt_dir = Path(PySide6.__file__).resolve().parent
ffmpeg_binaries = [
    (str(dll), "PySide6") for dll in qt_dir.glob("*.dll") if dll.name[:2] in {"av", "sw"}
]

datas = [
    (str(ROOT / "assets" / "icon.png"), "assets"),
    (str(ROOT / "assets" / "icon.ico"), "assets"),
]

a = Analysis(
    [str(ROOT / "packaging" / "launcher.py")],
    pathex=[str(ROOT / "src")],
    binaries=ffmpeg_binaries,
    datas=datas,
    hiddenimports=["PySide6.QtMultimedia"],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    # The AI extras are optional and huge; keep the release build lean.
    excludes=["tkinter", "torch", "librosa", "piano_transcription_inference", "matplotlib"],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="PianoWaterfall",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    icon=str(ICON),
    version=str(ROOT / "packaging" / "version_info.txt"),
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="PianoWaterfall",
)
