from __future__ import annotations

from piano_waterfall.app import APP_NAME, APP_VERSION, MainWindow


def test_main_window_builds(qapp, monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("PIANO_WATERFALL_DATA_DIR", str(tmp_path))
    window = MainWindow()
    try:
        assert APP_NAME in window.windowTitle() or "Piano Waterfall" in window.windowTitle()
        assert window.widget is not None
        assert window.widget.height() > 0
        assert not window._clock.loaded
        assert APP_VERSION.count(".") >= 1
        window.show()
        qapp.processEvents()
        assert window.isVisible()
    finally:
        window.close()
