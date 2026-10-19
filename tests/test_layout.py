from __future__ import annotations

import pytest

from piano_waterfall.layout import KeyboardLayout, fit_keyboard_range


def test_fit_range_keeps_full_piano() -> None:
    assert fit_keyboard_range(36, 96) == (36, 96)


def test_fit_range_pads_narrow_melody() -> None:
    low, high = fit_keyboard_range(60, 64)
    assert high - low >= 36
    assert low % 12 == 0
    assert high % 12 == 0


def test_fit_range_extreme_notes_stay_on_piano() -> None:
    for low, high in ((21, 21), (108, 108), (30, 100), (0, 200)):
        fitted_low, fitted_high = fit_keyboard_range(low, high)
        assert 21 <= fitted_low < fitted_high <= 108
        assert fitted_high - fitted_low >= 12


def test_layout_covers_requested_pitches() -> None:
    layout = KeyboardLayout(36, 96, 1200)
    keys = list(layout.keys())
    assert keys[0].pitch == 36
    assert keys[-1].pitch == 96
    assert len(keys) == 61
    assert len(layout.white_keys()) == 36
    assert len(layout.black_keys()) == 25


def test_white_keys_tile_without_gaps() -> None:
    layout = KeyboardLayout(36, 96, 1200)
    whites = layout.white_keys()
    assert whites[0].x == pytest.approx(0.0)
    for left, right in zip(whites, whites[1:], strict=False):
        assert left.x + left.width == pytest.approx(right.x)


def test_black_key_is_narrower_and_inside_board() -> None:
    layout = KeyboardLayout(36, 96, 1200)
    for key in layout.black_keys():
        assert key.black
        assert key.width < layout.white_width
        assert 0 <= key.x <= 1200 - key.width


def test_pitch_at_edges() -> None:
    layout = KeyboardLayout(36, 96, 1200)
    assert layout.pitch_at(0) == 36
    assert layout.pitch_at(1200) == 96
    assert layout.pitch_at(-1) is None
    assert layout.pitch_at(1201) is None
    assert layout.key(20) is None
