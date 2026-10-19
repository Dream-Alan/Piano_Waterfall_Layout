"""Grab a screenshot of the real application window.

Run from a source checkout:

    python scripts/screenshot_app.py "C:\\path\\song.mid" docs/screenshot.png --time 40
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

os.environ.setdefault("QT_QPA_FONTDIR", r"C:\Windows\Fonts")

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
os.environ.setdefault("PIANO_WATERFALL_DATA_DIR", str(ROOT / ".devdata"))

from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from piano_waterfall.app import MainWindow  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Screenshot the Piano Waterfall window")
    parser.add_argument("midi", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--time", type=float, default=40.0)
    parser.add_argument("--size", default="1280x800")
    parser.add_argument("--theme", default="neon")
    parser.add_argument("--voice", default="grand")
    parser.add_argument("--dock", action="store_true", help="show the transcription dock")
    args = parser.parse_args()

    width, _, height = args.size.lower().partition("x")
    app = QApplication([])
    app.setStyle("Fusion")

    window = MainWindow()
    window.resize(int(width), int(height))
    window.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen, True)
    window.show()
    window._set_theme(args.theme)  # noqa: SLF001 - dev helper
    window._dock.setVisible(args.dock)  # noqa: SLF001 - ignore saved layout
    window.set_voice(args.voice, reload=False)
    window._autoplay_button.setChecked(True)  # noqa: SLF001 - docs screenshot
    window.load_midi(args.midi, autoplay=False)

    deadline = time.monotonic() + 120
    while time.monotonic() < deadline and not window._clock.loaded:  # noqa: SLF001
        # QTest.qWait() holds the GIL and starves the render QThread; sleeping
        # releases it so the worker can make progress while we pump events.
        app.processEvents()
        time.sleep(0.02)

    if args.dock:
        window._dock.show()  # noqa: SLF001

    window._clock.pause()  # noqa: SLF001
    seconds = max(0.0, min(args.time, window._duration))  # noqa: SLF001
    window._seek.setValue(int(seconds * 1000))  # noqa: SLF001
    window._on_seek_released()  # noqa: SLF001 - keeps the playback clock in sync
    QTest.qWait(300)

    pixmap = window.grab()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    if not pixmap.save(str(args.output)):
        print(f"cannot write {args.output}", file=sys.stderr)
        return 1
    print(f"saved {args.output} ({pixmap.width()}x{pixmap.height()})")
    window.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
