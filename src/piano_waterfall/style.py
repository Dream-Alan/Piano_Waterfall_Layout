"""Dark Qt stylesheet built from the active waterfall theme."""

from __future__ import annotations

from PySide6.QtGui import QColor

from .theme import Theme


def build_stylesheet(theme: Theme) -> str:
    accent = theme.accent
    text = theme.text
    red, green, blue = QColor(accent).getRgb()[:3]
    accent_soft = f"rgba({red}, {green}, {blue}, 0.55)"
    accent_faint = f"rgba({red}, {green}, {blue}, 0.12)"
    accent_faint_hover = f"rgba({red}, {green}, {blue}, 0.22)"
    return f"""
    QMainWindow, QDialog {{
        background: #0a0e16;
    }}
    QWidget {{
        color: {text};
        font-family: "Microsoft YaHei UI", "Segoe UI", "PingFang SC", sans-serif;
        font-size: 13px;
    }}
    QWidget#TopBar {{
        background: rgba(255, 255, 255, 0.035);
        border-bottom: 1px solid rgba(255, 255, 255, 0.07);
    }}
    QWidget#Transport {{
        background: #0c111a;
        border-top: 1px solid rgba(255, 255, 255, 0.07);
    }}
    QLabel#AppTitle {{
        font-size: 15px;
        font-weight: 700;
        letter-spacing: 1.5px;
        color: {text};
    }}
    QLabel#FileLabel {{
        color: rgba(232, 246, 255, 0.62);
    }}
    QLabel#TimeLabel {{
        font-family: "Cascadia Mono", "Consolas", monospace;
        color: rgba(232, 246, 255, 0.75);
    }}
    QLabel#HintLabel {{
        color: rgba(232, 246, 255, 0.55);
    }}
    QPushButton, QToolButton {{
        background: rgba(255, 255, 255, 0.06);
        border: 1px solid rgba(255, 255, 255, 0.09);
        border-radius: 8px;
        padding: 6px 12px;
    }}
    QPushButton:hover, QToolButton:hover {{
        background: rgba(255, 255, 255, 0.13);
        border-color: rgba(255, 255, 255, 0.18);
    }}
    QPushButton:pressed, QToolButton:pressed {{
        background: rgba(255, 255, 255, 0.18);
    }}
    QPushButton:disabled, QToolButton:disabled {{
        color: rgba(232, 246, 255, 0.3);
        background: rgba(255, 255, 255, 0.03);
    }}
    QPushButton#AccentButton {{
        background: {accent};
        color: #071018;
        border: none;
        font-weight: 600;
    }}
    QPushButton#AccentButton:disabled {{
        background: rgba(255, 255, 255, 0.05);
        color: rgba(232, 246, 255, 0.30);
    }}
    QPushButton#AccentButton:hover {{
        background: {accent};
        border: 1px solid rgba(255, 255, 255, 0.55);
    }}
    QPushButton#SecondaryButton {{
        background: {accent_faint};
        color: {accent};
        border: 1px solid {accent_soft};
        font-weight: 600;
    }}
    QPushButton#SecondaryButton:hover {{
        background: {accent_faint_hover};
        border-color: {accent};
    }}
    QPushButton#SecondaryButton:pressed {{
        background: {accent_faint_hover};
    }}
    QPushButton#SecondaryButton:disabled {{
        color: rgba(232, 246, 255, 0.28);
        border-color: rgba(255, 255, 255, 0.10);
        background: rgba(255, 255, 255, 0.03);
    }}
    QPushButton#IconButton {{
        background: transparent;
        border: none;
        border-radius: 8px;
        padding: 6px;
    }}
    QPushButton#IconButton:hover {{
        background: rgba(255, 255, 255, 0.10);
    }}
    QPushButton#PlayButton {{
        background: {accent};
        border: none;
        border-radius: 22px;
        padding: 0px;
    }}
    QPushButton#PlayButton:hover {{
        border: 2px solid rgba(255, 255, 255, 0.65);
    }}
    QSlider::groove:horizontal {{
        height: 4px;
        background: rgba(255, 255, 255, 0.12);
        border-radius: 2px;
    }}
    QSlider::sub-page:horizontal {{
        background: {accent};
        border-radius: 2px;
    }}
    QSlider::handle:horizontal {{
        width: 12px;
        height: 12px;
        margin: -5px 0;
        border-radius: 7px;
        background: #ffffff;
        border: 2px solid {accent};
    }}
    QSlider::handle:horizontal:hover {{
        width: 14px;
        height: 14px;
        margin: -6px 0;
        border-radius: 8px;
    }}
    QComboBox {{
        background: rgba(255, 255, 255, 0.06);
        border: 1px solid rgba(255, 255, 255, 0.09);
        border-radius: 7px;
        padding: 4px 10px;
        min-width: 64px;
    }}
    QComboBox:hover {{
        background: rgba(255, 255, 255, 0.12);
    }}
    QComboBox::drop-down {{
        border: none;
        width: 18px;
    }}
    QComboBox QAbstractItemView {{
        background: #101722;
        border: 1px solid rgba(255, 255, 255, 0.10);
        selection-background-color: {accent};
        selection-color: #071018;
        outline: none;
    }}
    QDockWidget {{
        color: {text};
        background: #0d131d;
    }}
    QDockWidget::title {{
        background: #0d131d;
        padding: 8px 10px;
        border-bottom: 1px solid rgba(255, 255, 255, 0.07);
    }}
    QPlainTextEdit {{
        background: #080c14;
        border: 1px solid rgba(255, 255, 255, 0.07);
        border-radius: 8px;
        font-family: "Cascadia Mono", "Consolas", monospace;
        font-size: 12px;
        color: rgba(232, 246, 255, 0.82);
        padding: 6px;
    }}
    QProgressBar {{
        background: rgba(255, 255, 255, 0.08);
        border: none;
        border-radius: 4px;
        height: 8px;
        text-align: center;
        color: transparent;
    }}
    QProgressBar::chunk {{
        background: {accent};
        border-radius: 4px;
    }}
    QScrollBar:vertical {{
        background: transparent;
        width: 10px;
        margin: 2px;
    }}
    QScrollBar::handle:vertical {{
        background: rgba(255, 255, 255, 0.18);
        border-radius: 5px;
        min-height: 24px;
    }}
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
        height: 0px;
    }}
    QScrollBar:horizontal {{
        background: transparent;
        height: 10px;
        margin: 2px;
    }}
    QScrollBar::handle:horizontal {{
        background: rgba(255, 255, 255, 0.18);
        border-radius: 5px;
        min-width: 24px;
    }}
    QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
        width: 0px;
    }}
    QMenuBar {{
        background: #0a0e16;
        color: {text};
    }}
    QMenuBar::item {{
        background: transparent;
        padding: 4px 10px;
    }}
    QMenuBar::item:selected {{
        background: rgba(255, 255, 255, 0.10);
        border-radius: 6px;
    }}
    QMenu {{
        background: #101722;
        border: 1px solid rgba(255, 255, 255, 0.10);
        padding: 6px;
    }}
    QMenu::item {{
        padding: 6px 22px;
        border-radius: 6px;
    }}
    QMenu::item:selected {{
        background: {accent};
        color: #071018;
    }}
    QMenu::separator {{
        height: 1px;
        background: rgba(255, 255, 255, 0.08);
        margin: 4px 8px;
    }}
    QToolTip {{
        background: #101722;
        color: {text};
        border: 1px solid rgba(255, 255, 255, 0.12);
        padding: 4px 8px;
    }}
    QMessageBox {{
        background: #0d131d;
    }}
    """
