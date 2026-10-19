from __future__ import annotations

from dataclasses import fields as dataclass_fields

from piano_waterfall.theme import DEFAULT_THEME, THEMES, get_theme, theme_keys


def test_all_themes_are_well_formed() -> None:
    assert len(THEMES) >= 5
    for key, theme in THEMES.items():
        assert theme.key == key
        assert theme.name
        for field in dataclass_fields(theme):
            if field.name in {"key", "name"}:
                continue
            value = getattr(theme, field.name)
            assert value.startswith("#") and len(value) == 7, (key, field.name, value)
            int(value[1:], 16)


def test_unknown_theme_falls_back_to_default() -> None:
    assert get_theme(None).key == DEFAULT_THEME
    assert get_theme("no-such-theme") is THEMES[DEFAULT_THEME]
    assert theme_keys() == list(THEMES)
