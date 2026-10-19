"""Colour themes for the waterfall view.

Themes are plain data (hex strings) so they can be used from tests, the
headless renderer and the Qt widget without importing Qt.
"""

from __future__ import annotations

from dataclasses import dataclass, fields


@dataclass(frozen=True, slots=True)
class Theme:
    key: str
    name: str
    # Background
    bg_top: str
    bg_bottom: str
    glow: str
    # Notes
    note_top: str
    note_bottom: str
    note_border: str
    note_glow: str
    # Judgement line
    line: str
    line_glow: str
    # Keyboard
    white_top: str
    white_bottom: str
    black_top: str
    black_bottom: str
    white_pressed_top: str
    white_pressed_bottom: str
    black_pressed_top: str
    black_pressed_bottom: str
    key_separator: str
    key_label: str
    # Chrome
    accent: str
    text: str

    @property
    def title(self) -> str:
        return self.name


THEMES: dict[str, Theme] = {
    "neon": Theme(
        key="neon",
        name="霓虹青",
        bg_top="#080b12",
        bg_bottom="#111a2b",
        glow="#0a3a4a",
        note_top="#7fe9ff",
        note_bottom="#00a6d6",
        note_border="#d8fbff",
        note_glow="#00e5ff",
        line="#00f0ff",
        line_glow="#00b8d4",
        white_top="#fbfbfb",
        white_bottom="#d9dde3",
        black_top="#242832",
        black_bottom="#0b0d12",
        white_pressed_top="#d9fbff",
        white_pressed_bottom="#57d9ec",
        black_pressed_top="#00e5ff",
        black_pressed_bottom="#0a6f86",
        key_separator="#8b95a5",
        key_label="#5b6577",
        accent="#00e5ff",
        text="#e8f6ff",
    ),
    "aurora": Theme(
        key="aurora",
        name="极光紫",
        bg_top="#0b0716",
        bg_bottom="#1b1030",
        glow="#2a1455",
        note_top="#d9b8ff",
        note_bottom="#7c3aed",
        note_border="#f3e8ff",
        note_glow="#a855f7",
        line="#c084fc",
        line_glow="#7e22ce",
        white_top="#f7f4ff",
        white_bottom="#d9d0ea",
        black_top="#221a33",
        black_bottom="#0c0715",
        white_pressed_top="#f0d9ff",
        white_pressed_bottom="#c084fc",
        black_pressed_top="#a855f7",
        black_pressed_bottom="#6b21a8",
        key_separator="#8a7aa5",
        key_label="#6b5b87",
        accent="#c084fc",
        text="#f5edff",
    ),
    "amber": Theme(
        key="amber",
        name="琥珀金",
        bg_top="#120d06",
        bg_bottom="#241708",
        glow="#4a2c07",
        note_top="#ffe1a3",
        note_bottom="#e08a00",
        note_border="#fff4d6",
        note_glow="#ffb020",
        line="#ffc24d",
        line_glow="#d97706",
        white_top="#fffaf0",
        white_bottom="#e4d6bd",
        black_top="#2a2014",
        black_bottom="#100a05",
        white_pressed_top="#ffe9b8",
        white_pressed_bottom="#ffb020",
        black_pressed_top="#e08a00",
        black_pressed_bottom="#8a4b00",
        key_separator="#9c8a6b",
        key_label="#7a6a4e",
        accent="#ffb020",
        text="#fff3dc",
    ),
    "sakura": Theme(
        key="sakura",
        name="樱花粉",
        bg_top="#120810",
        bg_bottom="#241226",
        glow="#4a1e3e",
        note_top="#ffd0e0",
        note_bottom="#ff5c9e",
        note_border="#fff0f6",
        note_glow="#ff7ab6",
        line="#ff9ec7",
        line_glow="#e0447f",
        white_top="#fff7fa",
        white_bottom="#ead8e2",
        black_top="#2c1e28",
        black_bottom="#120a10",
        white_pressed_top="#ffe0ee",
        white_pressed_bottom="#ff9ec7",
        black_pressed_top="#ff5c9e",
        black_pressed_bottom="#b01f5b",
        key_separator="#a98a98",
        key_label="#8a6d7c",
        accent="#ff7ab6",
        text="#fff0f6",
    ),
    "classic": Theme(
        key="classic",
        name="经典蓝",
        bg_top="#0c1018",
        bg_bottom="#141c2b",
        glow="#1b2a44",
        note_top="#bcd7ff",
        note_bottom="#3b82f6",
        note_border="#eaf2ff",
        note_glow="#60a5fa",
        line="#93c5fd",
        line_glow="#2563eb",
        white_top="#f8fafc",
        white_bottom="#dbe3ee",
        black_top="#1f2937",
        black_bottom="#0b111b",
        white_pressed_top="#dbeafe",
        white_pressed_bottom="#93c5fd",
        black_pressed_top="#3b82f6",
        black_pressed_bottom="#1d4ed8",
        key_separator="#8fa1b8",
        key_label="#5c6c85",
        accent="#60a5fa",
        text="#eef4ff",
    ),
}

DEFAULT_THEME = "neon"


def get_theme(key: str | None) -> Theme:
    return THEMES.get(key or DEFAULT_THEME, THEMES[DEFAULT_THEME])


def theme_keys() -> list[str]:
    return list(THEMES)


__all__ = ["Theme", "THEMES", "DEFAULT_THEME", "get_theme", "theme_keys", "fields"]
