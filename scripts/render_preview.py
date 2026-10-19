"""Render a single waterfall frame to PNG without opening a window.

Useful for README screenshots, design iterations and CI smoke tests::

    python scripts/render_preview.py song.mid preview.png --time 12
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from PySide6.QtGui import QColor, QImage  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from piano_waterfall.midi_io import parse_midi  # noqa: E402
from piano_waterfall.waterfall import WaterfallWidget  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Render a waterfall frame to PNG")
    parser.add_argument("midi", type=Path, help="input .mid file")
    parser.add_argument("output", type=Path, help="output .png file")
    parser.add_argument("--time", type=float, default=8.0, help="playback time in seconds")
    parser.add_argument("--size", default="1280x720", help="WIDTHxHEIGHT")
    parser.add_argument("--theme", default="neon", help="neon, aurora, amber, sakura or classic")
    parser.add_argument("--fall-speed", type=float, default=430.0)
    parser.add_argument("--rainbow", action="store_true")
    parser.add_argument("--title", default="", help="caption shown in the frame")
    args = parser.parse_args()

    width, _, height = args.size.lower().partition("x")
    app = QApplication.instance() or QApplication([])  # noqa: F841

    song = parse_midi(args.midi)
    widget = WaterfallWidget()
    widget.resize(int(width), int(height))
    widget.set_song(song, title=args.title or args.midi.stem)
    widget.set_theme(args.theme)
    widget.set_fall_speed(args.fall_speed)
    widget.set_rainbow(args.rainbow)
    widget.set_time(max(0.0, args.time))

    image = QImage(widget.size(), QImage.Format.Format_ARGB32)
    image.fill(QColor("black"))
    widget.render(image)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    if not image.save(str(args.output)):
        print(f"无法写入 {args.output}", file=sys.stderr)
        return 1
    print(f"已写入 {args.output} ({image.width()}x{image.height()})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
