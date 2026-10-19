from __future__ import annotations

from piano_waterfall.app import APP_NAME, APP_VERSION, MainWindow
from piano_waterfall.synth import VOICES


def test_main_window_builds(qapp, monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("PIANO_WATERFALL_DATA_DIR", str(tmp_path))
    window = MainWindow()
    try:
        assert APP_NAME in window.windowTitle() or "Piano Waterfall" in window.windowTitle()
        assert window.widget is not None
        assert window.widget.height() > 0
        assert window._clock.loaded is False
        assert APP_VERSION.count(".") >= 1
        assert window._voice_combo.count() == len(VOICES)
        assert window._autoplay_button.isChecked()
        assert window._autoplay is True
        window._autoplay_button.setChecked(False)
        assert window._autoplay is False
        window.set_voice("felt", reload=False)
        assert window._voice_key == "felt"
        assert window._synth_settings().voice == "felt"
        window.show()
        qapp.processEvents()
        assert window.isVisible()
    finally:
        window.close()
