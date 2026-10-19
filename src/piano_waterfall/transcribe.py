"""Audio-to-MIDI transcription facade.

Two engines are available:

``"hft"``
    Sony's hFT-Transformer, bundled as a 22 MB ONNX model.  Fast and small.
``"crnn"``
    Kong et al.'s CRNN, exported to a 154 MB ONNX model.  More accurate, but
    downloaded on demand and stored in the user data directory.

The historical public names remain so the UI and tests have one import point.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from . import crnn, hft

TranscriptionUnavailable = hft.TranscriptionUnavailable
TranscriptionCancelled = hft.TranscriptionCancelled

ENGINES = ("hft", "crnn")
DEFAULT_ENGINE = "hft"
ENGINE_NAMES = {"hft": "快速 · hFT-Transformer", "crnn": "高精度 · CRNN"}

INSTALL_HINT = (
    "内置转录组件不完整（模型或 onnxruntime 缺失）。\n"
    "可以点击「一键下载 AI 模型」重新获取（约 22 MB），"
    "或重新安装 Piano Waterfall。"
)


def _module(engine: str):
    if engine == "crnn":
        return crnn
    return hft


def availability(engine: str = DEFAULT_ENGINE) -> tuple[bool, str]:
    return _module(engine).availability()


def model_path(engine: str = DEFAULT_ENGINE) -> Path | None:
    return _module(engine).model_path()


def download_model(
    engine: str = DEFAULT_ENGINE,
    *,
    progress: Callable[[int, int], None] | None = None,
    should_cancel: Callable[[], bool] | None = None,
) -> Path:
    return _module(engine).download_model(progress=progress, should_cancel=should_cancel)


def transcribe(
    audio_path: str | Path,
    midi_path: str | Path,
    *,
    engine: str = DEFAULT_ENGINE,
    device: str = "cpu",
    progress: Callable[[float, str], None] | None = None,
    should_cancel: Callable[[], bool] | None = None,
) -> Path:
    """Transcribe ``audio_path`` to ``midi_path`` with the chosen engine.

    ``device`` is accepted for backwards compatibility (ONNX always runs on
    the CPU; PyTorch is no longer involved).
    """

    del device
    if engine not in ENGINES:
        raise ValueError(f"未知的转录引擎：{engine}")
    return _module(engine).transcribe(
        audio_path,
        midi_path,
        progress=progress,
        should_cancel=should_cancel,
    )
