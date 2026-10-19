"""Entry point for the frozen (PyInstaller) build."""

import tempfile
import traceback
from pathlib import Path


def _log_crash(details: str) -> None:
    """Windowed builds have no stderr; leave a breadcrumb for support."""

    for directory in (Path(tempfile.gettempdir()), Path.cwd()):
        try:
            (directory / "piano-waterfall-crash.log").write_text(details, encoding="utf-8")
            return
        except OSError:
            continue


if __name__ == "__main__":
    try:
        from piano_waterfall.app import main

        raise SystemExit(main())
    except SystemExit:
        raise
    except BaseException:
        _log_crash(traceback.format_exc())
        raise
