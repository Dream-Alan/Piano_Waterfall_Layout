# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller recipe for a self-contained Windows build (onedir)."""

import sys
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

# conda's `_ctypes.pyd` links against `ffi.dll` from Library/bin, which the
# dependency scanner does not see because it is outside the normal DLL path.
ffi_dll = Path(sys.base_prefix) / "Library" / "bin" / "ffi.dll"
ffi_binaries = [(str(ffi_dll), ".")] if ffi_dll.exists() else []

datas = [
    (str(ROOT / "assets" / "icon.png"), "assets"),
    (str(ROOT / "assets" / "icon.ico"), "assets"),
    (str(ROOT / "src" / "piano_waterfall" / "assets" / "samples" / "piano"), "assets/samples/piano"),
    (str(ROOT / "src" / "piano_waterfall" / "assets" / "samples" / "ATTRIBUTION.md"), "assets/samples"),
    (
        str(ROOT / "src" / "piano_waterfall" / "assets" / "models" / "hft_transformer.onnx"),
        "assets/models",
    ),
    (
        str(ROOT / "src" / "piano_waterfall" / "assets" / "models" / "ATTRIBUTION.md"),
        "assets/models",
    ),
]

a = Analysis(
    [str(ROOT / "packaging" / "launcher.py")],
    pathex=[str(ROOT / "src")],
    binaries=ffmpeg_binaries + ffi_binaries,
    datas=datas,
    hiddenimports=["PySide6.QtMultimedia", "ctypes", "_ctypes", "soundfile", "onnxruntime"],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
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
