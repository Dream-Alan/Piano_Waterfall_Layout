"""Render the application icon into the repository.

Usage (from the project root)::

    python scripts/make_icons.py
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from PySide6.QtWidgets import QApplication  # noqa: E402

from piano_waterfall.icons import save_icon  # noqa: E402


def main() -> int:
    app = QApplication.instance() or QApplication([])
    del app

    png_targets = [
        ROOT / "assets" / "icon.png",
        ROOT / "src" / "piano_waterfall" / "assets" / "icon.png",
    ]
    for target in png_targets:
        target.parent.mkdir(parents=True, exist_ok=True)
        save_icon(str(target), 512)
        print("wrote", target)

    try:
        from PIL import Image
    except ImportError:
        print("Pillow not installed, skipping .ico", file=sys.stderr)
        return 0

    source = Image.open(png_targets[0]).convert("RGBA")
    ico_target = ROOT / "assets" / "icon.ico"
    source.save(
        ico_target,
        format="ICO",
        sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)],
    )
    print("wrote", ico_target)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
