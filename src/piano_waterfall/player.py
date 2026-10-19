"""Playback clock built on QtMultimedia with a silent fallback.

The waterfall is driven by :attr:`PlaybackClock.time`, which interpolates
between the coarse ``positionChanged`` signals of ``QMediaPlayer`` so the
animation stays smooth at 60 fps.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QElapsedTimer, QObject, QTimer, QUrl, Signal
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer


class PlaybackClock(QObject):
    position_changed = Signal(float)  # seconds, for coarse UI updates
    duration_changed = Signal(float)
    playing_changed = Signal(bool)
    finished = Signal()

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._player = QMediaPlayer(self)
        self._audio = QAudioOutput(self)
        self._player.setAudioOutput(self._audio)

        self._duration = 0.0
        self._last_position = 0.0
        self._last_update = QElapsedTimer()
        self._last_update.start()
        self._rate = 1.0
        self._playing = False
        self._loaded = False

        self._player.positionChanged.connect(self._on_position)
        self._player.durationChanged.connect(self._on_duration)
        self._player.playbackStateChanged.connect(self._on_state)
        self._player.mediaStatusChanged.connect(self._on_status)

        self._ticker = QTimer(self)
        self._ticker.setInterval(40)
        self._ticker.timeout.connect(self._emit_position)
        self._ticker.start()

    # ------------------------------------------------------------------ state
    @property
    def duration(self) -> float:
        return self._duration

    @property
    def playing(self) -> bool:
        return self._playing

    @property
    def loaded(self) -> bool:
        return self._loaded

    @property
    def time(self) -> float:
        if not self._playing:
            return (
                min(self._last_position, self._duration) if self._duration else self._last_position
            )
        elapsed = self._last_update.elapsed() / 1000.0 * self._rate
        return min(self._last_position + max(elapsed, 0.0), self._duration)

    # ---------------------------------------------------------------- loading
    def load(self, wav_path: str | Path, duration_hint: float) -> None:
        self._duration = float(duration_hint)
        self._last_position = 0.0
        self._loaded = True
        self._player.setSource(QUrl.fromLocalFile(str(Path(wav_path).resolve())))
        self._last_update.restart()
        self.duration_changed.emit(self._duration)

    def clear(self) -> None:
        self._player.stop()
        self._player.setSource(QUrl())
        self._loaded = False
        self._playing = False
        self._duration = 0.0
        self._last_position = 0.0
        self.playing_changed.emit(False)

    # --------------------------------------------------------------- controls
    def play(self) -> None:
        if not self._loaded:
            return
        if self._duration and self._last_position >= self._duration - 0.05:
            self.seek(0.0)
        self._player.play()
        self._last_update.restart()
        self._set_playing(True)

    def pause(self) -> None:
        self._player.pause()
        self._last_position = self.time
        self._set_playing(False)

    def toggle(self) -> None:
        if self._playing:
            self.pause()
        else:
            self.play()

    def stop(self) -> None:
        self._player.stop()
        self._last_position = 0.0
        self._set_playing(False)
        self.position_changed.emit(0.0)

    def seek(self, seconds: float) -> None:
        seconds = max(0.0, min(float(seconds), self._duration))
        self._player.setPosition(int(seconds * 1000))
        self._last_position = seconds
        self._last_update.restart()
        self.position_changed.emit(seconds)

    def set_rate(self, rate: float) -> None:
        self._rate = max(0.25, min(float(rate), 2.0))
        self._last_position = self.time
        self._last_update.restart()
        self._player.setPlaybackRate(self._rate)

    def set_volume(self, volume: float) -> None:
        self._audio.setVolume(max(0.0, min(float(volume), 1.0)))

    @property
    def rate(self) -> float:
        return self._rate

    # ---------------------------------------------------------------- signals
    def _set_playing(self, value: bool) -> None:
        if value != self._playing:
            self._playing = value
            self.playing_changed.emit(value)

    def _on_position(self, ms: int) -> None:
        self._last_position = ms / 1000.0
        self._last_update.restart()

    def _on_duration(self, ms: int) -> None:
        if ms > 0:
            self._duration = ms / 1000.0
            self.duration_changed.emit(self._duration)

    def _on_state(self, state) -> None:
        self._set_playing(state == QMediaPlayer.PlaybackState.PlayingState)
        if state == QMediaPlayer.PlaybackState.PlayingState:
            self._last_update.restart()

    def _on_status(self, status) -> None:
        if status == QMediaPlayer.MediaStatus.EndOfMedia:
            self._last_position = self._duration
            self._set_playing(False)
            self.finished.emit()

    def _emit_position(self) -> None:
        if self._loaded:
            self.position_changed.emit(self.time)
