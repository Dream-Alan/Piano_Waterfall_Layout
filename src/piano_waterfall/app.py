"""Piano Waterfall – desktop application window.

Run with ``python -m piano_waterfall`` or the ``piano-waterfall`` command.
"""

from __future__ import annotations

import argparse
import os
import sys
import traceback
import wave
from dataclasses import replace
from pathlib import Path

from PySide6.QtCore import QEvent, QSettings, QSize, Qt, QTimer, QUrl
from PySide6.QtGui import (
    QAction,
    QActionGroup,
    QDesktopServices,
    QFontMetrics,
    QKeySequence,
    QShortcut,
)
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QDockWidget,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QSizePolicy,
    QSlider,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from . import transcribe
from .icons import icon, load_window_icon
from .midi_io import MidiError, format_time, parse_midi
from .paths import app_data_dir, audio_cache_dir, cached_audio_path, transcriptions_dir
from .player import PlaybackClock
from .style import build_stylesheet
from .synth import DEFAULT_SETTINGS, DEFAULT_VOICE, VOICES, SynthSettings, get_voice, voice_choices
from .theme import DEFAULT_THEME, THEMES, get_theme
from .waterfall import WaterfallWidget
from .workers import ModelDownloadWorker, RenderWorker, TranscriptionWorker

APP_NAME = "Piano Waterfall"
APP_TAGLINE = "钢琴瀑布流"
APP_VERSION = "1.3.0"
GITHUB_URL = "https://github.com/Dream-Alan/Piano_Waterfall_Layout"

MIDI_SUFFIXES = {".mid", ".midi"}
AUDIO_SUFFIXES = {".mp3", ".wav", ".flac", ".ogg", ".m4a", ".aac", ".aiff", ".opus"}
TICK_MS = 16


def _as_int(value, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _as_float(value, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _as_bool(value, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self._settings = QSettings(str(app_data_dir() / "settings.ini"), QSettings.Format.IniFormat)
        self._song = None
        self._midi_path: Path | None = None
        self._duration = 0.0
        self._seeking = False
        self._pending_play = False
        self._last_painted = -1.0
        self._render_worker: RenderWorker | None = None
        self._render_target: Path | None = None
        self._transcribe_worker: TranscriptionWorker | None = None
        self._model_worker: ModelDownloadWorker | None = None
        self._transcribe_messages: set[str] = set()
        self._muted = False
        self._volume_before_mute = 80
        self._theme_name = DEFAULT_THEME
        self._voice_key = DEFAULT_VOICE
        self._autoplay = True
        self._resume_at = 0.0
        self._theme_actions: dict[str, QAction] = {}
        self._closing = False

        self._last_dir = str(self._settings.value("last_dir", str(Path.home() / "Music")))

        self.setWindowTitle(f"{APP_NAME} · {APP_TAGLINE}")
        self.setWindowIcon(load_window_icon())
        self.setMinimumSize(900, 600)
        self.setAcceptDrops(True)

        self._clock = PlaybackClock(self)
        self._build_ui()
        self._build_menus()
        self._build_transcribe_dock()
        self._connect_signals()

        self._restore_settings()

        self._tick_timer = QTimer(self)
        self._tick_timer.setTimerType(Qt.TimerType.PreciseTimer)
        self._tick_timer.setInterval(TICK_MS)
        self._tick_timer.timeout.connect(self._on_tick)
        self._tick_timer.start()

        self.statusBar().showMessage(
            "空格 播放/暂停 · 双击画面 全屏 · 也可以直接把 MIDI / 音频拖进窗口", 8000
        )
        if not self._transcribe_available:
            self._log_transcription("提示：内置转录模型缺失，可在面板中点击「一键下载 AI 模型」。")
            self._log_transcription(transcribe.INSTALL_HINT)

    # --------------------------------------------------------------- UI build
    def _build_ui(self) -> None:
        central = QWidget(self)
        layout = QVBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self._top_bar = self._build_top_bar()
        layout.addWidget(self._top_bar)

        self.widget = WaterfallWidget(self)
        layout.addWidget(self.widget, 1)

        self._transport = self._build_transport()
        layout.addWidget(self._transport)

        self.setCentralWidget(central)

    def _build_top_bar(self) -> QWidget:
        bar = QFrame(self)
        bar.setObjectName("TopBar")
        row = QHBoxLayout(bar)
        row.setContentsMargins(18, 12, 18, 12)
        row.setSpacing(12)

        logo = QLabel(bar)
        logo.setPixmap(load_window_icon().pixmap(28, 28))
        logo.setFixedSize(28, 28)
        logo.setScaledContents(True)
        row.addWidget(logo)

        titles = QVBoxLayout()
        titles.setSpacing(1)
        title = QLabel("PIANO WATERFALL", bar)
        title.setObjectName("AppTitle")
        tagline = QLabel(APP_TAGLINE, bar)
        tagline.setObjectName("HintLabel")
        self._tagline_label = tagline
        titles.addWidget(title)
        titles.addWidget(tagline)
        row.addLayout(titles)

        row.addSpacing(18)
        self._file_label = QLabel("尚未加载文件", bar)
        self._file_label.setObjectName("FileLabel")
        row.addWidget(self._file_label)
        row.addStretch(1)

        self._open_button = QPushButton(icon("folder", "#e8f6ff"), "打开 MIDI", bar)
        self._open_button.setObjectName("AccentButton")
        self._open_button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        row.addWidget(self._open_button)

        self._transcribe_button_top = QPushButton(icon("ai", "#e8f6ff"), "音频转 MIDI", bar)
        self._transcribe_button_top.setObjectName("SecondaryButton")
        self._transcribe_button_top.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        row.addWidget(self._transcribe_button_top)

        self._autoplay_button = QPushButton("自动播放", bar)
        self._autoplay_button.setObjectName("ToggleButton")
        self._autoplay_button.setCheckable(True)
        self._autoplay_button.setChecked(True)
        self._autoplay_button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._autoplay_button.setToolTip("打开文件后自动播放，可随时开关")
        row.addWidget(self._autoplay_button)

        self._voice_combo = QComboBox(bar)
        self._voice_combo.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._voice_combo.setMinimumWidth(128)
        for voice in voice_choices():
            self._voice_combo.addItem(voice.name, voice.key)
            self._voice_combo.setItemData(
                self._voice_combo.count() - 1,
                f"{voice.description}\n切换后会重新合成并缓存该音色",
                Qt.ItemDataRole.ToolTipRole,
            )
        self._voice_combo.setToolTip("选择钢琴音色")
        row.addWidget(self._voice_combo)

        self._theme_combo = QComboBox(bar)
        self._theme_combo.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        for key, theme in THEMES.items():
            self._theme_combo.addItem(theme.name, key)
        self._theme_combo.setToolTip("切换配色主题")
        row.addWidget(self._theme_combo)

        self._fullscreen_button = QToolButton(bar)
        self._fullscreen_button.setObjectName("IconButton")
        self._fullscreen_button.setIcon(icon("fullscreen"))
        self._fullscreen_button.setIconSize(QSize(18, 18))
        self._fullscreen_button.setToolTip("全屏 (F11)")
        self._fullscreen_button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        row.addWidget(self._fullscreen_button)

        return bar

    def _build_transport(self) -> QWidget:
        bar = QFrame(self)
        bar.setObjectName("Transport")
        row = QHBoxLayout(bar)
        row.setContentsMargins(16, 10, 16, 10)
        row.setSpacing(10)

        self._play_button = QPushButton(bar)
        self._play_button.setObjectName("PlayButton")
        self._play_button.setFixedSize(44, 44)
        self._play_button.setIconSize(QSize(20, 20))
        self._play_button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._play_button.setToolTip("播放 / 暂停 (空格)")
        row.addWidget(self._play_button)

        self._restart_button = QToolButton(bar)
        self._restart_button.setObjectName("IconButton")
        self._restart_button.setIcon(icon("restart", "#e8f6ff"))
        self._restart_button.setIconSize(QSize(18, 18))
        self._restart_button.setToolTip("回到开头")
        self._restart_button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        row.addWidget(self._restart_button)

        self._time_label = QLabel("00:00", bar)
        self._time_label.setObjectName("TimeLabel")
        self._time_label.setFixedWidth(48)
        self._time_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        row.addWidget(self._time_label)

        self._seek = QSlider(Qt.Orientation.Horizontal, bar)
        self._seek.setRange(0, 0)
        self._seek.setSingleStep(1000)
        self._seek.setPageStep(5000)
        self._seek.setMinimumWidth(200)
        self._seek.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._seek.setToolTip("拖动跳转到任意位置")
        row.addWidget(self._seek, 1)

        self._duration_label = QLabel("00:00", bar)
        self._duration_label.setObjectName("TimeLabel")
        self._duration_label.setFixedWidth(48)
        self._duration_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        row.addWidget(self._duration_label)

        row.addSpacing(8)
        self._rate_combo = QComboBox(bar)
        self._rate_combo.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        for label, value in (
            ("0.5×", 0.5),
            ("0.75×", 0.75),
            ("1.0×", 1.0),
            ("1.25×", 1.25),
            ("1.5×", 1.5),
        ):
            self._rate_combo.addItem(label, value)
        self._rate_combo.setToolTip("播放速度")
        row.addWidget(self._rate_combo)

        speed_title = QLabel("下落", bar)
        speed_title.setObjectName("HintLabel")
        row.addWidget(speed_title)
        self._speed_slider = QSlider(Qt.Orientation.Horizontal, bar)
        self._speed_slider.setRange(140, 1100)
        self._speed_slider.setFixedWidth(96)
        self._speed_slider.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._speed_slider.setToolTip("音符下落速度")
        row.addWidget(self._speed_slider)

        row.addSpacing(4)
        self._volume_button = QToolButton(bar)
        self._volume_button.setObjectName("IconButton")
        self._volume_button.setIcon(icon("volume", "#e8f6ff"))
        self._volume_button.setIconSize(QSize(18, 18))
        self._volume_button.setToolTip("静音 / 取消静音")
        self._volume_button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        row.addWidget(self._volume_button)

        self._volume_slider = QSlider(Qt.Orientation.Horizontal, bar)
        self._volume_slider.setRange(0, 100)
        self._volume_slider.setFixedWidth(84)
        self._volume_slider.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._volume_slider.setToolTip("音量")
        row.addWidget(self._volume_slider)

        return bar

    def _build_menus(self) -> None:
        file_menu = self.menuBar().addMenu("文件(&F)")
        open_action = QAction("打开 MIDI 或音频…", self)
        open_action.setShortcut(QKeySequence.StandardKey.Open)
        open_action.triggered.connect(self.open_file_dialog)
        file_menu.addAction(open_action)

        transcribe_action = QAction("音频转 MIDI…", self)
        transcribe_action.setShortcut(QKeySequence("Ctrl+T"))
        transcribe_action.triggered.connect(lambda: self._toggle_transcribe_dock(force_open=True))
        file_menu.addAction(transcribe_action)
        file_menu.addSeparator()

        quit_action = QAction("退出", self)
        quit_action.setShortcut(QKeySequence.StandardKey.Quit)
        quit_action.triggered.connect(self.close)
        file_menu.addAction(quit_action)

        self._view_menu = self.menuBar().addMenu("视图(&V)")
        view_menu = self._view_menu
        theme_menu = view_menu.addMenu("配色主题")
        group = QActionGroup(self)
        group.setExclusive(True)
        for key, theme in THEMES.items():
            action = QAction(theme.name, self)
            action.setCheckable(True)
            action.setData(key)
            action.triggered.connect(lambda _checked=False, k=key: self._set_theme(k))
            group.addAction(action)
            theme_menu.addAction(action)
            self._theme_actions[key] = action

        self._rainbow_action = QAction("彩虹音符", self)
        self._rainbow_action.setCheckable(True)
        self._rainbow_action.setShortcut(QKeySequence("Ctrl+R"))
        self._rainbow_action.toggled.connect(self.widget.set_rainbow)
        view_menu.addAction(self._rainbow_action)
        view_menu.addSeparator()

        self._fullscreen_action = QAction("全屏", self)
        self._fullscreen_action.setCheckable(True)
        self._fullscreen_action.setShortcut(QKeySequence("F11"))
        self._fullscreen_action.triggered.connect(self._toggle_fullscreen)
        view_menu.addAction(self._fullscreen_action)

        help_menu = self.menuBar().addMenu("帮助(&H)")
        shortcuts_action = QAction("快捷键…", self)
        shortcuts_action.setShortcut(QKeySequence("F1"))
        shortcuts_action.triggered.connect(self._show_shortcuts)
        help_menu.addAction(shortcuts_action)
        about_action = QAction("关于 Piano Waterfall…", self)
        about_action.triggered.connect(self._show_about)
        help_menu.addAction(about_action)
        help_menu.addSeparator()
        github_action = QAction("访问 GitHub 项目主页", self)
        github_action.triggered.connect(lambda: QDesktopServices.openUrl(QUrl(GITHUB_URL)))
        help_menu.addAction(github_action)

    def _build_transcribe_dock(self) -> None:
        self._dock = QDockWidget("音频转 MIDI", self)
        self._dock.setObjectName("TranscribeDock")
        self._dock.setAllowedAreas(
            Qt.DockWidgetArea.RightDockWidgetArea | Qt.DockWidgetArea.LeftDockWidgetArea
        )
        self._dock.setFeatures(
            QDockWidget.DockWidgetFeature.DockWidgetClosable
            | QDockWidget.DockWidgetFeature.DockWidgetMovable
        )

        panel = QWidget(self._dock)
        panel.setMinimumWidth(340)
        column = QVBoxLayout(panel)
        column.setContentsMargins(14, 14, 14, 14)
        column.setSpacing(10)

        intro = QLabel(
            "内置 hFT-Transformer 模型（22 MB），无需安装 PyTorch。\n"
            "把 MP3 / WAV / FLAC 识别成 MIDI，再用瀑布流播放。",
            panel,
        )
        intro.setObjectName("HintLabel")
        intro.setWordWrap(True)
        column.addWidget(intro)

        status_row = QHBoxLayout()
        status_label = QLabel("模型状态", panel)
        status_label.setObjectName("HintLabel")
        status_row.addWidget(status_label)
        self._model_status = QLabel(panel)
        self._model_status.setObjectName("HintLabel")
        self._model_status.setWordWrap(True)
        status_row.addWidget(self._model_status, 1)
        column.addLayout(status_row)

        self._transcribe_button = QPushButton(icon("ai", "#071018"), "选择音频并转录", panel)
        self._transcribe_button.setObjectName("AccentButton")
        self._transcribe_button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        column.addWidget(self._transcribe_button)

        controls = QHBoxLayout()
        self._cancel_button = QPushButton("取消", panel)
        self._cancel_button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._cancel_button.hide()
        controls.addWidget(self._cancel_button)
        self._install_button = QPushButton("一键下载 AI 模型", panel)
        self._install_button.setObjectName("SecondaryButton")
        self._install_button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._install_button.hide()
        controls.addWidget(self._install_button)
        controls.addStretch(1)
        column.addLayout(controls)

        self._transcribe_progress = QProgressBar(panel)
        self._transcribe_progress.setRange(0, 100)
        self._transcribe_progress.setTextVisible(False)
        self._transcribe_progress.hide()
        column.addWidget(self._transcribe_progress)

        self._transcribe_log = QPlainTextEdit(panel)
        self._transcribe_log.setReadOnly(True)
        self._transcribe_log.setPlaceholderText("转录日志会显示在这里…")
        self._transcribe_log.setMinimumHeight(160)
        column.addWidget(self._transcribe_log, 1)

        self._dock.setWidget(panel)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self._dock)
        self._dock.hide()

        self._transcribe_available, self._transcribe_detail = transcribe.availability()
        self._refresh_model_status()

        dock_toggle = self._dock.toggleViewAction()
        dock_toggle.setText("音频转 MIDI 面板")
        self._view_menu.addAction(dock_toggle)

    def _connect_signals(self) -> None:
        self._open_button.clicked.connect(self.open_file_dialog)
        self._transcribe_button_top.clicked.connect(
            lambda: self._toggle_transcribe_dock(force_open=True)
        )
        self._transcribe_button.clicked.connect(self._choose_audio)
        self._cancel_button.clicked.connect(self._cancel_transcription)
        self._install_button.clicked.connect(self._confirm_model_download)
        self._theme_combo.currentIndexChanged.connect(self._on_theme_combo)
        self._voice_combo.currentIndexChanged.connect(self._on_voice_combo)
        self._autoplay_button.toggled.connect(self._on_autoplay_toggled)
        self._fullscreen_button.clicked.connect(self._toggle_fullscreen)
        self._play_button.clicked.connect(self._toggle_play)
        self._restart_button.clicked.connect(self._restart)

        self._seek.sliderPressed.connect(self._on_seek_pressed)
        self._seek.sliderMoved.connect(self._on_seek_drag)
        self._seek.sliderReleased.connect(self._on_seek_released)
        self._rate_combo.currentIndexChanged.connect(self._on_rate_changed)
        self._speed_slider.valueChanged.connect(self._on_speed_changed)
        self._volume_slider.valueChanged.connect(self._on_volume_changed)
        self._volume_button.clicked.connect(self._toggle_mute)

        self._clock.playing_changed.connect(self._on_playing_changed)
        self._clock.duration_changed.connect(self._on_duration_changed)
        self._clock.finished.connect(self._on_finished)

        self._dock.visibilityChanged.connect(self._on_dock_visibility)

        space = QShortcut(QKeySequence(Qt.Key.Key_Space), self)
        space.setContext(Qt.ShortcutContext.ApplicationShortcut)
        space.activated.connect(self._toggle_play)

        escape = QShortcut(QKeySequence(Qt.Key.Key_Escape), self)
        escape.setContext(Qt.ShortcutContext.ApplicationShortcut)
        escape.activated.connect(self._exit_fullscreen)

    # -------------------------------------------------------------- settings
    def _restore_settings(self) -> None:
        self.set_voice(str(self._settings.value("voice", DEFAULT_VOICE)), reload=False)
        self._set_theme(str(self._settings.value("theme", DEFAULT_THEME)))

        autoplay = _as_bool(self._settings.value("autoplay", True), True)
        self._autoplay = autoplay
        self._autoplay_button.blockSignals(True)
        self._autoplay_button.setChecked(autoplay)
        self._autoplay_button.blockSignals(False)

        self._speed_slider.blockSignals(True)
        self._speed_slider.setValue(_as_int(self._settings.value("fall_speed", 430), 430))
        self._speed_slider.blockSignals(False)
        self.widget.set_fall_speed(self._speed_slider.value())

        volume = _as_int(self._settings.value("volume", 78), 78)
        self._volume_slider.blockSignals(True)
        self._volume_slider.setValue(volume)
        self._volume_slider.blockSignals(False)
        self._clock.set_volume(volume / 100)

        rate = _as_float(self._settings.value("rate", 1.0), 1.0)
        index = self._rate_combo.findData(rate)
        if index < 0:
            index = self._rate_combo.findData(1.0)
        self._rate_combo.blockSignals(True)
        self._rate_combo.setCurrentIndex(index)
        self._rate_combo.blockSignals(False)

        rainbow = _as_bool(self._settings.value("rainbow", False))
        self._rainbow_action.setChecked(rainbow)
        self.widget.set_rainbow(rainbow)

        geometry = self._settings.value("geometry")
        if geometry is not None:
            self.restoreGeometry(geometry)
        else:
            self.resize(1180, 760)
            screen = QApplication.primaryScreen()
            if screen is not None:
                available = screen.availableGeometry()
                self.move(
                    available.center().x() - self.width() // 2,
                    available.center().y() - self.height() // 2,
                )

        state = self._settings.value("window_state")
        if state is not None:
            self.restoreState(state)

        self._sync_transport_state()

    def _save_settings(self) -> None:
        self._settings.setValue("theme", self._theme_name)
        self._settings.setValue("voice", self._voice_key)
        self._settings.setValue("autoplay", self._autoplay)
        self._settings.setValue("fall_speed", self._speed_slider.value())
        self._settings.setValue("volume", self._volume_slider.value())
        self._settings.setValue("rate", self._rate_combo.currentData())
        self._settings.setValue("rainbow", self._rainbow_action.isChecked())
        self._settings.setValue("geometry", self.saveGeometry())
        self._settings.setValue("window_state", self.saveState())
        self._settings.setValue("last_dir", self._last_dir)

    # --------------------------------------------------------------- theming
    def _on_autoplay_toggled(self, checked: bool) -> None:
        self._autoplay = bool(checked)
        self._settings.setValue("autoplay", self._autoplay)
        if not self._autoplay:
            self._pending_play = False
        self.statusBar().showMessage(
            "自动播放已开启：打开文件后立即播放"
            if self._autoplay
            else "自动播放已关闭：打开文件后停在开头",
            2500,
        )

    def _on_voice_combo(self, index: int) -> None:
        key = self._voice_combo.itemData(index)
        if key:
            self.set_voice(str(key))

    def set_voice(self, name: str, *, reload: bool = True) -> None:
        """Select a piano voice; re-render the current song when needed."""

        if name not in VOICES:
            name = DEFAULT_VOICE
        changed = name != self._voice_key
        self._voice_key = name
        self._settings.setValue("voice", name)

        self._voice_combo.blockSignals(True)
        index = self._voice_combo.findData(name)
        if index >= 0:
            self._voice_combo.setCurrentIndex(index)
        self._voice_combo.blockSignals(False)

        if reload and changed and self._song is not None and self._midi_path is not None:
            self._resume_at = self._clock.time
            self._pending_play = self._clock.playing
            self._clock.pause()
            self._cancel_render()
            self.statusBar().showMessage(f"正在切换音色：{get_voice(name).name}…")
            self._prepare_audio(self._midi_path, self._song)

    def _synth_settings(self) -> SynthSettings:
        return replace(DEFAULT_SETTINGS, voice=self._voice_key)

    def _on_theme_combo(self, index: int) -> None:
        key = self._theme_combo.itemData(index)
        if key:
            self._set_theme(str(key))

    def _set_theme(self, name: str) -> None:
        if name not in THEMES:
            name = DEFAULT_THEME
        self._theme_name = name
        theme = get_theme(name)

        self.widget.set_theme(theme)
        app = QApplication.instance()
        if app is not None:
            app.setStyleSheet(build_stylesheet(theme))

        self._theme_combo.blockSignals(True)
        index = self._theme_combo.findData(name)
        if index >= 0:
            self._theme_combo.setCurrentIndex(index)
        self._theme_combo.blockSignals(False)

        for key, action in self._theme_actions.items():
            action.setChecked(key == name)

        self._play_button.setIcon(icon("pause" if self._clock.playing else "play", "#071018"))
        self._restart_button.setIcon(icon("restart", theme.text))
        self._volume_button.setIcon(icon("volume", theme.text))
        self._fullscreen_button.setIcon(
            icon("fullscreen_exit" if self.isFullScreen() else "fullscreen", theme.text)
        )

    # -------------------------------------------------------------- playback
    def _toggle_play(self) -> None:
        if self._song is None:
            self.statusBar().showMessage("先打开一个 MIDI 或音频文件", 4000)
            return
        if self._clock.loaded:
            self._clock.toggle()
            if not self._clock.playing and not self._pending_play:
                self._sync_transport_state()
        else:
            self._pending_play = True
            if self._midi_path is not None:
                self._prepare_audio(self._midi_path, self._song)

    def _restart(self) -> None:
        if self._song is None:
            return
        self._clock.seek(0.0)
        self.widget.set_time(0.0)
        self._seek.setValue(0)
        self._time_label.setText(format_time(0.0))
        self._last_painted = 0.0

    def _on_playing_changed(self, playing: bool) -> None:
        self._play_button.setIcon(icon("pause" if playing else "play", "#071018"))
        self._play_button.setToolTip("暂停 (空格)" if playing else "播放 (空格)")

    def _on_duration_changed(self, duration: float) -> None:
        if duration <= 0:
            return
        self._duration = duration
        maximum = int(duration * 1000)
        if self._seek.maximum() != maximum:
            self._seek.setRange(0, maximum)
        self._duration_label.setText(format_time(duration))

    def _on_tick(self) -> None:
        if self._song is None or not self._clock.loaded:
            return
        current = min(self._clock.time, self._duration or self._clock.time)
        if self._clock.playing or abs(current - self._last_painted) > 0.001:
            self.widget.set_time(current)
            self._last_painted = current
            self._time_label.setText(format_time(current))
            if not self._seeking:
                self._seek.setValue(int(current * 1000))

    def _on_finished(self) -> None:
        self.widget.set_time(self._duration)
        self._last_painted = self._duration
        self._seek.setValue(int(self._duration * 1000))
        self._time_label.setText(format_time(self._duration))
        self.statusBar().showMessage("播放结束，按空格从头再听一次", 5000)

    def _on_seek_pressed(self) -> None:
        self._seeking = True

    def _on_seek_drag(self, value: int) -> None:
        seconds = value / 1000.0
        self._time_label.setText(format_time(seconds))
        self.widget.set_time(seconds)
        self._last_painted = seconds

    def _on_seek_released(self) -> None:
        value = self._seek.value() / 1000.0
        self._clock.seek(value)
        self.widget.set_time(value)
        self._last_painted = value
        self._time_label.setText(format_time(value))
        self._seeking = False

    def _on_rate_changed(self, index: int) -> None:
        rate = self._rate_combo.itemData(index)
        if rate is None:
            return
        self._clock.set_rate(float(rate))
        self.statusBar().showMessage(f"播放速度 {rate}×", 2500)

    def _on_speed_changed(self, value: int) -> None:
        self.widget.set_fall_speed(value)

    def _on_volume_changed(self, value: int) -> None:
        if not self._muted:
            self._clock.set_volume(value / 100)
            self._volume_before_mute = value
        if value > 0 and self._muted:
            self._muted = False
            self._update_volume_icon()

    def _toggle_mute(self) -> None:
        if self._muted:
            self._muted = False
            self._volume_slider.blockSignals(True)
            self._volume_slider.setValue(self._volume_before_mute or 78)
            self._volume_slider.blockSignals(False)
            self._clock.set_volume((self._volume_before_mute or 78) / 100)
        else:
            if self._volume_slider.value() > 0:
                self._volume_before_mute = self._volume_slider.value()
            self._muted = True
            self._volume_slider.blockSignals(True)
            self._volume_slider.setValue(0)
            self._volume_slider.blockSignals(False)
            self._clock.set_volume(0.0)
        self._update_volume_icon()

    def _update_volume_icon(self) -> None:
        color = get_theme(self._theme_name).text
        self._volume_button.setIcon(icon("volume", color))

    # ------------------------------------------------------------ file flow
    def _sync_transport_state(self) -> None:
        self._play_button.setEnabled(True)
        self._seek.setEnabled(self._song is not None)
        self._restart_button.setEnabled(self._song is not None)

    def open_file_dialog(self) -> None:
        filters = (
            "MIDI 与音频 (*.mid *.midi *.mp3 *.wav *.flac *.ogg *.m4a *.aac *.aiff *.opus);;"
            "MIDI 文件 (*.mid *.midi);;"
            "音频文件 (*.mp3 *.wav *.flac *.ogg *.m4a *.aac *.aiff *.opus);;"
            "所有文件 (*)"
        )
        path, _ = QFileDialog.getOpenFileName(self, "打开 MIDI 或音频", self._last_dir, filters)
        if not path:
            return
        self._last_dir = str(Path(path).parent)
        self.open_path(path)

    def open_path(self, path: str | Path, *, autoplay: bool | None = None) -> None:
        target = Path(path)
        if not target.is_file():
            QMessageBox.warning(self, "文件不存在", f"找不到文件：\n{target}")
            return
        suffix = target.suffix.lower()
        if suffix in MIDI_SUFFIXES:
            self.load_midi(target, autoplay=autoplay)
        elif suffix in AUDIO_SUFFIXES:
            self.start_transcription(target)
        else:
            QMessageBox.information(
                self,
                "不支持的文件",
                f"无法识别 {target.suffix or '该'} 格式。\n可以打开 MIDI，或 MP3 / WAV / FLAC 等音频。",
            )

    def load_midi(self, path: str | Path, *, autoplay: bool | None = None) -> None:
        target = Path(path)
        try:
            song = parse_midi(target)
        except MidiError as exc:
            QMessageBox.critical(self, "无法读取 MIDI", str(exc))
            return
        except Exception as exc:  # pragma: no cover - safety net
            QMessageBox.critical(self, "无法读取 MIDI", f"{target.name}\n\n{exc}")
            return

        self._cancel_render()
        self._clock.clear()
        self._song = song
        self._midi_path = target
        self._duration = song.duration
        self._last_painted = -1.0
        self._pending_play = self._autoplay if autoplay is None else bool(autoplay)
        self._resume_at = 0.0

        self.widget.set_song(song, title=target.stem)
        self.widget.set_theme(self._theme_name)
        self.widget.set_fall_speed(self._speed_slider.value())
        self.widget.set_rainbow(self._rainbow_action.isChecked())

        self.setWindowTitle(f"{target.stem} · {APP_NAME}")
        self._file_label.setText(self._elide(target.name, 260))
        self._file_label.setToolTip(str(target))

        self._seek.setRange(0, int(song.duration * 1000))
        self._seek.setValue(0)
        self._time_label.setText("00:00")
        self._duration_label.setText(format_time(song.duration))
        self._sync_transport_state()

        self.statusBar().showMessage(
            f"已加载 {target.name} · {len(song.notes)} 个音符 · {format_time(song.duration)}",
            6000,
        )
        self._prepare_audio(target, song)

    # ---------------------------------------------------------- piano audio
    def _prepare_audio(self, midi_path: Path, song) -> None:
        settings = self._synth_settings()
        cached = cached_audio_path(midi_path, settings)
        if cached.exists() and cached.stat().st_size > 4096:
            self._load_audio(cached, song)
            return
        self._start_render(midi_path, song, cached, settings)

    def _start_render(self, midi_path: Path, song, cached: Path, settings) -> None:
        self._render_target = cached
        self.widget.show_overlay(
            "正在合成钢琴音频",
            "首次打开这首曲子（或切换音色）需要渲染，完成后会缓存，下次秒开。",
            None,
        )
        worker = RenderWorker(song, midi_path, cached, settings)
        self._render_worker = worker
        worker.progress.connect(self._on_render_progress)
        worker.succeeded.connect(self._on_render_succeeded)
        worker.failed.connect(self._on_render_failed)
        worker.finished.connect(self._cleanup_render_worker)
        self.statusBar().showMessage("正在合成钢琴音频…")
        worker.start()

    def _on_render_progress(self, fraction: float, message: str) -> None:
        if fraction < 0:
            return
        self.widget.show_overlay(
            "正在合成钢琴音频",
            message or "正在渲染…",
            max(0.0, min(1.0, fraction)),
        )

    def _on_render_succeeded(self, wav_path: str) -> None:
        if self._render_target is None or Path(wav_path) != self._render_target:
            return  # a stale worker from a previously opened file
        self.widget.hide_overlay()
        if self._song is not None:
            self._load_audio(Path(wav_path), self._song)

    def _on_render_failed(self, message: str) -> None:
        self.widget.hide_overlay()
        if self._closing or self._render_target is None:
            return
        if "取消" in message:
            self.statusBar().showMessage("已取消音频合成", 3000)
            return
        self.statusBar().showMessage(f"音频合成失败，改为静音播放：{message}", 10000)
        self._log_transcription(f"音频合成失败（将静音播放）：{message}")
        QMessageBox.warning(
            self,
            "音频合成失败",
            f"{message}\n\n瀑布流仍可播放，但这次没有声音。\n"
            "如果文件放在只读目录，请把音频缓存目录设到可写位置。",
        )
        if self._song is not None:
            self._load_silent_audio(self._song)

    def _cleanup_render_worker(self) -> None:
        worker = self._render_worker
        if worker is not None and not worker.isRunning():
            self._render_worker = None

    def _cancel_render(self) -> None:
        self._render_target = None
        worker = self._render_worker
        if worker is not None and worker.isRunning():
            worker.cancel()
            worker.wait(2000)
        self._render_worker = None

    def _load_audio(self, wav_path: Path, song) -> None:
        resume = self._resume_at
        self._resume_at = 0.0
        self._clock.load(wav_path, song.duration)
        self._clock.set_rate(float(self._rate_combo.currentData()))
        self._clock.set_volume(self._volume_slider.value() / 100)
        self._duration = max(song.duration, self._clock.duration)
        self._duration_label.setText(format_time(self._duration))
        self._seek.setRange(0, int(self._duration * 1000))
        if resume > 0.05:
            self._clock.seek(min(resume, self._duration))
        if self._pending_play:
            self._pending_play = False
            self._clock.play()
        else:
            self.statusBar().showMessage("准备就绪，按空格开始播放", 4000)

    def _load_silent_audio(self, song) -> None:
        path = audio_cache_dir() / f"silence-{int(max(song.duration, 1))}.wav"
        if not path.exists():
            try:
                self._write_silence(path, max(song.duration, 1.0))
            except OSError:
                return
        self._pending_play = False
        self._load_audio(path, song)

    @staticmethod
    def _write_silence(path: Path, seconds: float) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temp = path.with_suffix(".part")
        with wave.open(str(temp), "wb") as handle:
            handle.setnchannels(2)
            handle.setsampwidth(2)
            handle.setframerate(44100)
            chunk = b"\x00\x00\x00\x00" * 44100
            remaining = int(seconds)
            for _ in range(remaining):
                handle.writeframes(chunk)
        temp.replace(path)

    # ------------------------------------------------------------ fullscreen
    def _toggle_fullscreen(self) -> None:
        if self.isFullScreen():
            self.showNormal()
        else:
            self.showFullScreen()

    def _exit_fullscreen(self) -> None:
        if self.isFullScreen():
            self.showNormal()

    def _sync_fullscreen_ui(self) -> None:
        fullscreen = self.isFullScreen()
        self._fullscreen_action.setChecked(fullscreen)
        theme = get_theme(self._theme_name)
        self._fullscreen_button.setIcon(
            icon("fullscreen_exit" if fullscreen else "fullscreen", theme.text)
        )
        self._fullscreen_button.setToolTip("退出全屏 (F11 / Esc)" if fullscreen else "全屏 (F11)")
        self._top_bar.setVisible(not fullscreen)
        self.menuBar().setVisible(not fullscreen)
        if fullscreen:
            self.statusBar().showMessage("按 Esc 或 F11 退出全屏", 4000)

    def changeEvent(self, event) -> None:  # noqa: N802 (Qt naming)
        if event.type() == QEvent.Type.WindowStateChange:
            self._sync_fullscreen_ui()
        super().changeEvent(event)

    # ---------------------------------------------------------- transcription
    def _toggle_transcribe_dock(self, *, force_open: bool = False) -> None:
        if force_open or not self._dock.isVisible():
            self._dock.show()
            self._dock.raise_()
        else:
            self._dock.hide()

    def _refresh_model_status(self) -> None:
        if self._transcribe_available:
            self._model_status.setText("已内置 · 22 MB")
            self._model_status.setToolTip(self._transcribe_detail or "内置 hFT-Transformer 已就绪")
            self._install_button.hide()
            self._dock.setWindowTitle("音频转 MIDI")
            self._transcribe_button.setToolTip("选择音频并转录")
        else:
            self._model_status.setText(self._transcribe_detail or "模型缺失")
            self._model_status.setToolTip(self._transcribe_detail or "")
            self._install_button.show()
            self._dock.setWindowTitle("音频转 MIDI（需要下载模型）")
            self._transcribe_button.setToolTip("请先下载内置转录模型")

    def _on_dock_visibility(self, visible: bool) -> None:
        if visible and not self._transcribe_available and not self._transcribe_log.toPlainText():
            self._log_transcription(transcribe.INSTALL_HINT)
        self._apply_compact_layout()

    def _apply_compact_layout(self) -> None:
        """Trim the top bar when the transcription dock steals horizontal space."""

        compact = self._dock.isVisible() and self.width() < 1500
        self._tagline_label.setVisible(not compact)
        self._file_label.setVisible(not compact)
        if compact:
            self._transcribe_button_top.setToolTip("把音频转录成 MIDI")
            self._voice_combo.setMinimumWidth(108)
        else:
            self._transcribe_button_top.setToolTip("把音频转录成 MIDI")
            self._voice_combo.setMinimumWidth(128)

    def resizeEvent(self, event) -> None:  # noqa: N802 (Qt naming)
        super().resizeEvent(event)
        self._apply_compact_layout()

    def _confirm_model_download(self) -> None:
        if self._model_worker is not None and self._model_worker.isRunning():
            return
        answer = QMessageBox.question(
            self,
            "下载 AI 转录模型",
            "内置转录模型缺失或已损坏，需要重新下载（约 22 MB）。\n\n"
            "下载完成后即可离线使用，是否继续？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.Yes,
        )
        if answer == QMessageBox.StandardButton.Yes:
            self._start_model_download()

    def _start_model_download(self) -> None:
        if self._model_worker is not None and self._model_worker.isRunning():
            return
        self._toggle_transcribe_dock(force_open=True)
        self._log_transcription("开始下载内置转录模型（约 22 MB）…")
        self._transcribe_progress.setRange(0, 100)
        self._transcribe_progress.setValue(0)
        self._transcribe_progress.show()
        self._cancel_button.show()
        self._cancel_button.setEnabled(True)
        self._transcribe_button.setEnabled(False)
        self._install_button.setEnabled(False)
        self.statusBar().showMessage("正在下载 AI 模型…")

        worker = ModelDownloadWorker(self)
        self._model_worker = worker
        worker.progress.connect(self._on_model_progress)
        worker.succeeded.connect(self._on_model_downloaded)
        worker.failed.connect(self._on_model_failed)
        worker.finished.connect(self._cleanup_model_worker)
        worker.start()

    def _on_model_progress(self, done: int, total: int) -> None:
        if total > 0:
            percent = int(done * 100 / total)
            self._transcribe_progress.setRange(0, 100)
            self._transcribe_progress.setValue(percent)
            self.statusBar().showMessage(
                f"正在下载 AI 模型… {done / 1e6:.1f} / {total / 1e6:.1f} MB"
            )

    def _finish_model_ui(self) -> None:
        self._transcribe_progress.hide()
        self._transcribe_progress.setRange(0, 100)
        self._transcribe_progress.setValue(0)
        self._cancel_button.hide()
        self._cancel_button.setEnabled(True)
        self._transcribe_button.setEnabled(True)
        self._install_button.setEnabled(True)

    def _on_model_downloaded(self, path: str) -> None:
        self._finish_model_ui()
        self._transcribe_available, self._transcribe_detail = transcribe.availability()
        self._refresh_model_status()
        self._log_transcription(f"模型下载完成：{path}")
        self.statusBar().showMessage("AI 模型已就绪，可以开始转录", 5000)
        if not self._transcribe_available:
            QMessageBox.warning(
                self,
                "仍不可用",
                "模型下载完成，但 onnxruntime 不可用，请重新安装 Piano Waterfall。",
            )

    def _on_model_failed(self, message: str) -> None:
        self._finish_model_ui()
        self._log_transcription(f"模型下载失败：{message}")
        self.statusBar().showMessage("模型下载失败", 5000)
        QMessageBox.warning(self, "下载失败", message)

    def _cleanup_model_worker(self) -> None:
        worker = self._model_worker
        if worker is not None and not worker.isRunning():
            self._model_worker = None

    def _choose_audio(self) -> None:
        if not self._transcribe_available:
            self._confirm_model_download()
            return
        path, _ = QFileDialog.getOpenFileName(
            self,
            "选择要转录的音频",
            self._last_dir,
            "音频 (*.mp3 *.wav *.flac *.ogg *.m4a *.aac *.aiff *.opus);;所有文件 (*)",
        )
        if not path:
            return
        self._last_dir = str(Path(path).parent)
        self.start_transcription(path)

    def start_transcription(self, audio_path: str | Path) -> None:
        if not self._transcribe_available:
            self._confirm_model_download()
            return
        if self._transcribe_worker is not None and self._transcribe_worker.isRunning():
            QMessageBox.information(self, "正在转录", "请等当前转录任务完成，或先取消它。")
            return

        audio = Path(audio_path)
        if not audio.is_file():
            QMessageBox.warning(self, "文件不存在", f"找不到音频文件：\n{audio}")
            return

        self._toggle_transcribe_dock(force_open=True)
        self._transcribe_messages.clear()
        self._log_transcription("─" * 46)
        self._log_transcription(f"开始转录：{audio.name}")
        self._transcribe_progress.setRange(0, 0)
        self._transcribe_progress.show()
        self._transcribe_button.setEnabled(False)
        self._cancel_button.show()
        self.statusBar().showMessage(f"正在转录 {audio.name}…")

        midi_path = transcriptions_dir() / f"{audio.stem}.mid"
        worker = TranscriptionWorker(audio, midi_path, self)
        self._transcribe_worker = worker
        worker.progress.connect(self._on_transcribe_progress)
        worker.succeeded.connect(self._on_transcribe_succeeded)
        worker.failed.connect(self._on_transcribe_failed)
        worker.finished.connect(self._cleanup_transcribe_worker)
        worker.start()

    def _on_transcribe_progress(self, fraction: float, message: str) -> None:
        message = (message or "").strip()
        if message and message not in self._transcribe_messages:
            self._transcribe_messages.add(message)
            self._log_transcription(message)
        if fraction < 0:
            self._transcribe_progress.setRange(0, 0)
        else:
            self._transcribe_progress.setRange(0, 100)
            self._transcribe_progress.setValue(int(max(0.0, min(1.0, fraction)) * 100))

    def _on_transcribe_succeeded(self, midi_path: str) -> None:
        self._finish_transcription_ui()
        self._log_transcription(f"完成，MIDI 已保存到：{midi_path}")
        self.statusBar().showMessage("转录完成，正在打开 MIDI", 5000)
        self.load_midi(Path(midi_path), autoplay=self._autoplay)

    def _on_transcribe_failed(self, message: str) -> None:
        self._finish_transcription_ui()
        if "取消" in message:
            self._log_transcription("已取消转录。")
            self.statusBar().showMessage("已取消转录", 3000)
            return
        self._log_transcription(f"转录失败：{message}")
        self.statusBar().showMessage("转录失败", 5000)
        box = QMessageBox(self)
        box.setWindowTitle("转录失败")
        box.setIcon(QMessageBox.Icon.Critical)
        box.setText("音频转 MIDI 失败。")
        box.setDetailedText(message)
        box.exec()

    def _finish_transcription_ui(self) -> None:
        self._transcribe_progress.hide()
        self._transcribe_progress.setRange(0, 100)
        self._transcribe_progress.setValue(0)
        self._transcribe_button.setEnabled(True)
        self._cancel_button.hide()

    def _cleanup_transcribe_worker(self) -> None:
        worker = self._transcribe_worker
        if worker is not None and not worker.isRunning():
            self._transcribe_worker = None

    def _cancel_transcription(self) -> None:
        cancelled = False
        worker = self._transcribe_worker
        if worker is not None and worker.isRunning():
            worker.cancel()
            cancelled = True
        model_worker = self._model_worker
        if model_worker is not None and model_worker.isRunning():
            model_worker.cancel()
            cancelled = True
        if cancelled:
            self._log_transcription("正在取消…")
            self._cancel_button.setEnabled(False)
            QTimer.singleShot(1500, lambda: self._cancel_button.setEnabled(True))

    def _log_transcription(self, message: str) -> None:
        self._transcribe_log.appendPlainText(message)

    # --------------------------------------------------------------- dialogs
    def _show_shortcuts(self) -> None:
        QMessageBox.information(
            self,
            "快捷键",
            "<b>播放控制</b><br>"
            "<b>空格</b>　播放 / 暂停<br>"
            "<b>F11 / 双击画面</b>　全屏切换<br>"
            "<b>Esc</b>　退出全屏<br><br>"
            "<b>文件</b><br>"
            "<b>Ctrl+O</b>　打开 MIDI 或音频<br>"
            "<b>Ctrl+T</b>　音频转 MIDI 面板<br>"
            "<b>Ctrl+R</b>　彩虹音符<br>"
            "<b>Ctrl+Q</b>　退出",
        )

    def _show_about(self) -> None:
        theme = get_theme(self._theme_name)
        html = (
            f"<h2 style='margin-bottom:2px'>Piano Waterfall "
            f"<span style='color:{theme.accent};font-size:13px'>v{APP_VERSION}</span></h2>"
            f"<p style='color:#8fa3b8;margin-top:0'>{APP_TAGLINE} · 把音乐变成下落的霓虹音符</p>"
            "<p>钢琴音色基于 <a href='https://github.com/nbrosowsky/tonejs-instruments'>"
            "tonejs-instruments</a> 的 VSCO 2 Community Edition 采样（CC-BY 3.0），"
            "本项目做了裁剪、单声道化与响度归一化；瀑布流渲染、播放控制与界面为原创实现"
            "（MIT License）。<br>"
            "音频转 MIDI 使用 Sony 的 "
            "<a href='https://github.com/sony/hFT-Transformer'>hFT-Transformer</a>"
            "（MIT License），在应用内以 ONNX Runtime 本地运行，无需 PyTorch。</p>"
            f"<p><a href='{GITHUB_URL}'>{GITHUB_URL}</a></p>"
            "<p style='color:#8fa3b8'>用 PySide6 与 NumPy 构建，可在 Windows / macOS / Linux 运行。</p>"
        )
        box = QMessageBox(self)
        box.setWindowTitle("关于 Piano Waterfall")
        box.setIconPixmap(load_window_icon().pixmap(64, 64))
        box.setTextFormat(Qt.TextFormat.RichText)
        box.setText(html)
        github_button = box.addButton("打开 GitHub", QMessageBox.ButtonRole.ActionRole)
        box.addButton("关闭", QMessageBox.ButtonRole.AcceptRole)
        box.exec()
        if box.clickedButton() is github_button:
            QDesktopServices.openUrl(QUrl(GITHUB_URL))

    # -------------------------------------------------------------- drag&drop
    def dragEnterEvent(self, event) -> None:  # noqa: N802
        if self._dropped_path(event) is not None:
            event.acceptProposedAction()
        else:
            super().dragEnterEvent(event)

    def dropEvent(self, event) -> None:  # noqa: N802
        path = self._dropped_path(event)
        if path is None:
            super().dropEvent(event)
            return
        event.acceptProposedAction()
        self._last_dir = str(path.parent)
        self.open_path(path)

    @staticmethod
    def _dropped_path(event) -> Path | None:
        mime = event.mimeData()
        if not mime.hasUrls():
            return None
        for url in mime.urls():
            if not url.isLocalFile():
                continue
            path = Path(url.toLocalFile())
            if path.suffix.lower() in MIDI_SUFFIXES | AUDIO_SUFFIXES:
                return path
        return None

    # ------------------------------------------------------------------ misc
    @staticmethod
    def _elide(text: str, width: int) -> str:
        metrics = QFontMetrics(QApplication.font())
        return metrics.elidedText(text, Qt.TextElideMode.ElideMiddle, width)

    def closeEvent(self, event) -> None:  # noqa: N802
        self._closing = True
        self._save_settings()
        self._clock.pause()
        self._cancel_render()
        worker = self._transcribe_worker
        if worker is not None and worker.isRunning():
            worker.cancel()
            worker.wait(2000)
        model_worker = self._model_worker
        if model_worker is not None and model_worker.isRunning():
            model_worker.cancel()
            model_worker.wait(2000)
        super().closeEvent(event)


def _transcribe_cli(audio: Path, output: str | None) -> int:
    """Headless audio-to-MIDI path, also used to smoke-test frozen builds."""

    import faulthandler

    from . import hft

    log_path = transcriptions_dir() / "transcribe-cli.log"
    log = log_path.open("w", encoding="utf-8", buffering=1)
    faulthandler.enable(file=log)
    faulthandler.dump_traceback_later(240, exit=True, file=log)

    def emit(message: str) -> None:
        print(message, file=log)
        if sys.stdout is not None:
            print(message, flush=True)

    try:
        if not audio.is_file():
            emit(f"找不到音频文件：{audio}")
            return 2
        destination = Path(output) if output else transcriptions_dir() / f"{audio.stem}.mid"
        emit(f"音频：{audio}")
        emit(f"模型：{hft.model_path()}")
        last = -1

        def progress(fraction: float, message: str) -> None:
            nonlocal last
            percent = int(fraction * 100)
            if percent != last:
                last = percent
                emit(f"[{percent:3d}%] {message}")

        try:
            result = hft.transcribe(audio, destination, progress=progress)
        except Exception as exc:
            emit(f"转录失败：{exc}")
            log.write(traceback.format_exc())
            return 1
        emit(f"转录完成：{result}")
        return 0
    finally:
        faulthandler.cancel_dump_traceback_later()
        log.close()


def main(argv: list[str] | None = None) -> int:
    arguments = list(argv if argv is not None else sys.argv)
    parser = argparse.ArgumentParser(
        prog="piano-waterfall",
        description="Piano Waterfall – MIDI waterfall player with offline piano synthesis.",
    )
    parser.add_argument("--version", "-V", action="store_true", help="print version and exit")
    parser.add_argument("--fullscreen", action="store_true", help="start in fullscreen")
    parser.add_argument(
        "--smoke-test", action="store_true", help="open the window, then quit (used by CI)"
    )
    parser.add_argument(
        "--voice",
        default=DEFAULT_VOICE,
        choices=list(VOICES),
        help="piano voice (default: %(default)s)",
    )
    parser.add_argument(
        "--transcribe",
        metavar="AUDIO",
        help="transcribe an audio file to MIDI without opening the window",
    )
    parser.add_argument(
        "--out",
        metavar="MIDI",
        help="output path for --transcribe (default: app data directory)",
    )
    parser.add_argument("files", nargs="*", help="MIDI or audio file to open")
    args, _unknown = parser.parse_known_args(arguments[1:])

    if args.version:
        print(f"Piano Waterfall {APP_VERSION}")
        return 0

    if args.transcribe:
        return _transcribe_cli(Path(args.transcribe), args.out)

    app = QApplication([arguments[0]])
    app.setApplicationName(APP_NAME)
    app.setApplicationDisplayName(APP_NAME)
    app.setOrganizationName("PianoWaterfall")
    app.setApplicationVersion(APP_VERSION)
    app.setStyle("Fusion")
    app.setWindowIcon(load_window_icon())

    window = MainWindow()
    window.set_voice(args.voice, reload=False)
    if args.fullscreen:
        window.showFullScreen()
    else:
        window.show()

    if args.files:
        QTimer.singleShot(120, lambda: window.open_path(args.files[0]))
    if args.smoke_test:
        # Used by packaging CI: start, load nothing, then exit without a user.
        # PIANO_WATERFALL_SMOKE_MS can extend the run to exercise audio rendering.
        smoke_ms = int(os.environ.get("PIANO_WATERFALL_SMOKE_MS", "1500"))
        QTimer.singleShot(smoke_ms, app.quit)

    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
