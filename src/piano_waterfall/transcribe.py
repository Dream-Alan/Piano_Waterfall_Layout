"""Audio-to-MIDI transcription facade.

The old implementation needed PyTorch, librosa and a 200 MB model download.
The app now ships Sony's hFT-Transformer as a 22 MB ONNX model, so the only
runtime dependency is onnxruntime.  This module keeps the historical public
names so the UI and tests have a single, stable import point.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from . import hft

TranscriptionUnavailable = hft.TranscriptionUnavailable
TranscriptionCancelled = hft.TranscriptionCancelled

INSTALL_HINT = (
    "内置转录组件不完整（模型或 onnxruntime 缺失）。\n"
    "可以点击「一键下载 AI 模型」重新获取（约 22 MB），"
    "或重新安装 Piano Waterfall。"
)


def availability() -> tuple[bool, str]:
    return hft.availability()


def model_path() -> Path | None:
    return hft.model_path()


def download_model(
    *,
    progress: Callable[[int, int], None] | None = None,
    should_cancel: Callable[[], bool] | None = None,
) -> Path:
    return hft.download_model(progress=progress, should_cancel=should_cancel)


def transcribe(
    audio_path: str | Path,
    midi_path: str | Path,
    *,
    device: str = "cpu",
    progress: Callable[[float, str], None] | None = None,
    should_cancel: Callable[[], bool] | None = None,
) -> Path:
    """Transcribe ``audio_path`` to ``midi_path``.

    ``device`` is accepted for backwards compatibility (the ONNX model always
    runs on the CPU; PyTorch is no longer involved).
    """

    del device
    return hft.transcribe(
        audio_path,
        midi_path,
        progress=progress,
        should_cancel=should_cancel,
    )
