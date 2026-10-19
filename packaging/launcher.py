"""Entry point for the frozen (PyInstaller) build."""

from piano_waterfall.app import main

if __name__ == "__main__":
    raise SystemExit(main())
