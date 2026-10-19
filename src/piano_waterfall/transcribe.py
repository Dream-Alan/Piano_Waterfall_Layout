"""Optional AI audio-to-MIDI transcription.

The heavy dependencies (torch, librosa, piano-transcription-inference) are
imported lazily so that the player itself only needs PySide6, numpy, mido and
soundfile.  ``pip install "piano-waterfall[ai]"`` enables this module.
"""

from __future__ import annotations

import importlib.util
import os
from collections.abc import Callable
from pathlib import Path

ProgressFn = Callable[[float, str], None]
CancelFn = Callable[[], bool]

SAMPLE_RATE = 16_000

INSTALL_HINT = (
    "未安装 AI 转录依赖。请在终端运行：\n\n"
    '    pip install "piano-waterfall[ai]"\n\n'
    "（或手动安装 torch、librosa、piano-transcription-inference）"
)


class TranscriptionUnavailable(RuntimeError):
    """The optional AI dependencies are missing or broken."""


class TranscriptionCancelled(RuntimeError):
    """The user cancelled the transcription."""


def _module_exists(name: str) -> bool:
    """Cheap presence check: never imports torch on application start-up."""

    try:
        return importlib.util.find_spec(name) is not None
    except (ImportError, ValueError):  # pragma: no cover - broken install
        return False


def availability() -> tuple[bool, str]:
    """Return ``(available, detail)`` without importing the heavy packages."""

    missing = [
        label
        for module, label in (
            ("librosa", "librosa"),
            ("torch", "torch"),
            ("piano_transcription_inference", "piano-transcription-inference"),
        )
        if not _module_exists(module)
    ]
    if missing:
        return False, "缺少依赖：" + "、".join(missing)
    return True, "AI 转录可用"


def _patch_torch_load() -> None:
    """Torch >= 2.6 defaults ``weights_only=True``; old checkpoints break."""

    try:
        import torch
    except Exception:  # pragma: no cover
        return

    if getattr(torch, "_pw_torch_load_patched", False):
        return
    original = torch.load

    def load(*args, **kwargs):
        kwargs.setdefault("weights_only", False)
        try:
            return original(*args, **kwargs)
        except TypeError:
            kwargs.pop("weights_only", None)
            return original(*args, **kwargs)

    torch.load = load  # type: ignore[assignment]
    torch._pw_torch_load_patched = True


def pick_device(preferred: str = "auto") -> str:
    if preferred and preferred != "auto":
        return preferred
    try:
        import torch

        return "cuda" if torch.cuda.is_available() else "cpu"
    except Exception:  # pragma: no cover
        return "cpu"


def transcribe(
    audio_path: str | Path,
    midi_path: str | Path,
    *,
    device: str = "auto",
    progress: ProgressFn | None = None,
    should_cancel: CancelFn | None = None,
) -> Path:
    """Convert an audio file to a MIDI file with Kong et al.'s model."""

    audio_path = Path(audio_path)
    midi_path = Path(midi_path)
    if not audio_path.exists():
        raise FileNotFoundError(f"找不到音频文件：{audio_path}")

    def report(fraction: float, message: str) -> None:
        if progress is not None:
            progress(fraction, message)
        if should_cancel is not None and should_cancel():
            raise TranscriptionCancelled

    try:
        import librosa
    except Exception as exc:  # pragma: no cover
        raise TranscriptionUnavailable(INSTALL_HINT) from exc

    try:
        import piano_transcription_inference as pti
    except Exception as exc:  # pragma: no cover
        raise TranscriptionUnavailable(INSTALL_HINT) from exc

    report(0.02, "正在读取音频…")
    try:
        audio, sr = librosa.load(str(audio_path), sr=SAMPLE_RATE, mono=True)
    except Exception as exc:
        raise RuntimeError(
            f"音频解码失败：{audio_path.name}\n"
            "mp3/m4a 等格式若无法解码，可先安装 ffmpeg 再重试。\n"
            f"原始错误：{exc}"
        ) from exc
    if sr != SAMPLE_RATE:  # librosa should have resampled already
        audio = librosa.resample(audio, orig_sr=sr, target_sr=SAMPLE_RATE)
    report(0.10, f"音频读取成功（{len(audio) / SAMPLE_RATE:.1f} 秒）")

    _patch_torch_load()

    chosen = pick_device(device)
    report(0.18, f"正在加载 AI 模型（{chosen.upper()}），首次运行会自动下载权重…")
    try:
        transcriptor = pti.PianoTranscription(device=chosen)
    except Exception as exc:  # pragma: no cover - model download
        raise RuntimeError(
            "AI 模型加载失败。首次运行需要联网下载约 200MB 权重；\n"
            "如果下载失败，可配置代理后重试。\n"
            f"原始错误：{exc}"
        ) from exc

    if should_cancel is not None and should_cancel():
        raise TranscriptionCancelled

    report(0.35, "正在转录（CPU 上通常需要音频时长的 0.3–1 倍）…")
    midi_path.parent.mkdir(parents=True, exist_ok=True)

    # The upstream API is transcribe(audio, midi_path); it writes the file.
    try:
        with _quiet_stdout():
            transcriptor.transcribe(audio, str(midi_path))
    except Exception as exc:  # pragma: no cover - model runtime
        raise RuntimeError(
            "转录过程中出错（可能是内存不足）。\n"
            "可以尝试更短的音频或关闭其他程序。\n"
            f"原始错误：{exc}"
        ) from exc

    if not midi_path.exists():
        raise RuntimeError("转录结束但没有生成 MIDI 文件，请查看日志。")

    report(1.0, "转录完成")
    return midi_path


class _quiet_stdout:
    """Redirect Python-level stdout/stderr to devnull (the model is chatty)."""

    def __enter__(self):
        self._saved = (os.dup(1), os.dup(2))
        self._devnull = os.open(os.devnull, os.O_WRONLY)
        os.dup2(self._devnull, 1)
        os.dup2(self._devnull, 2)

    def __exit__(self, *exc_info):
        os.dup2(self._saved[0], 1)
        os.dup2(self._saved[1], 2)
        os.close(self._devnull)
        os.close(self._saved[0])
        os.close(self._saved[1])
        return False
