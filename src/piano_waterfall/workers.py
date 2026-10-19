"""Background workers for transcription and audio rendering.

Both jobs emit progress messages that the UI shows in a small console panel,
and both can be cancelled cooperatively.
"""

from __future__ import annotations

import traceback
from pathlib import Path

from PySide6.QtCore import QThread, Signal

from . import transcribe
from .midi_io import Song
from .synth import DEFAULT_SETTINGS, RenderCancelled, SynthSettings, render_song, write_wav


class TranscriptionWorker(QThread):
    progress = Signal(float, str)
    succeeded = Signal(str)
    failed = Signal(str)

    def __init__(self, audio_path: str | Path, midi_path: str | Path, parent=None):
        super().__init__(parent)
        self.audio_path = Path(audio_path)
        self.midi_path = Path(midi_path)
        self._cancelled = False

    def cancel(self) -> None:
        self._cancelled = True

    def run(self) -> None:
        try:
            result = transcribe.transcribe(
                self.audio_path,
                self.midi_path,
                progress=lambda fraction, message: self.progress.emit(fraction, message),
                should_cancel=lambda: self._cancelled,
            )
        except transcribe.TranscriptionCancelled:
            self.failed.emit("已取消转录")
        except Exception as exc:  # pragma: no cover - UI path
            self.failed.emit(str(exc))
        else:
            self.succeeded.emit(str(result))


class ModelDownloadWorker(QThread):
    """Fetch the bundled transcription model if it is missing or damaged."""

    progress = Signal(int, int)
    succeeded = Signal(str)
    failed = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._cancelled = False

    def cancel(self) -> None:
        self._cancelled = True

    def run(self) -> None:
        from . import hft

        try:
            path = hft.download_model(
                progress=lambda done, total: self.progress.emit(done, total),
                should_cancel=lambda: self._cancelled,
            )
        except hft.TranscriptionCancelled:
            self.failed.emit("已取消下载")
        except Exception as exc:  # pragma: no cover - UI path
            traceback.print_exc()
            self.failed.emit(f"下载 AI 模型失败：{exc}")
        else:
            self.succeeded.emit(str(path))


class RenderWorker(QThread):
    progress = Signal(float, str)
    succeeded = Signal(str)
    failed = Signal(str)

    def __init__(
        self,
        song: Song,
        midi_path: str | Path,
        wav_path: str | Path,
        settings: SynthSettings = DEFAULT_SETTINGS,
        parent=None,
    ):
        super().__init__(parent)
        self.song = song
        self.midi_path = Path(midi_path)
        self.wav_path = Path(wav_path)
        self.settings = settings
        self._cancelled = False

    def cancel(self) -> None:
        self._cancelled = True

    def run(self) -> None:
        try:
            audio = render_song(
                self.song,
                self.settings,
                progress=lambda fraction, message: self.progress.emit(fraction, message),
                should_cancel=lambda: self._cancelled,
            )
        except RenderCancelled:
            self.failed.emit("已取消音频合成")
            return
        except Exception as exc:  # pragma: no cover - UI path
            traceback.print_exc()
            self.failed.emit(str(exc))
            return
        temp_path = self.wav_path.with_name(self.wav_path.name + ".part")
        try:
            write_wav(temp_path, audio, self.settings.sample_rate)
        except Exception as exc:  # pragma: no cover
            traceback.print_exc()
            temp_path.unlink(missing_ok=True)
            self.failed.emit(f"写入音频失败：{exc}")
            return
        if self._cancelled:
            temp_path.unlink(missing_ok=True)
            self.failed.emit("已取消音频合成")
            return
        try:
            temp_path.replace(self.wav_path)
        except OSError as exc:  # pragma: no cover - file locked by player
            temp_path.unlink(missing_ok=True)
            self.failed.emit(f"写入音频失败：{exc}")
            return
        self.succeeded.emit(str(self.wav_path))
