"""
Fade project root resolver — works in dev AND PyInstaller frozen bundle.

Usage (in any backend module):
    from backend._root import PROJECT_ROOT, user_data_dir

    db_path = PROJECT_ROOT / "fade_tasks.db"
    cache   = user_data_dir() / "cache"
"""
from __future__ import annotations
import os
import sys
from pathlib import Path


def _resolve_root() -> Path:
    """
    Returns the project root directory regardless of how the code is running:
      - Dev mode   : repo root (two levels up from backend/_root.py)
      - PyInstaller: the extracted _internal bundle dir (_MEIPASS)
      - Packaged   : FADE_RESOURCES_PATH env var set by Electron
    """
    # 1. Electron sets this before spawning the backend
    resources = os.environ.get("FADE_RESOURCES_PATH", "")
    if resources:
        return Path(resources)

    # 2. PyInstaller frozen bundle
    if getattr(sys, "frozen", False):
        meipass = getattr(sys, "_MEIPASS", None)
        if meipass:
            return Path(meipass)

    # 3. Normal Python / dev mode — backend/_root.py is at <root>/backend/_root.py
    return Path(__file__).resolve().parent.parent


#: Absolute path to the project / resource root.
PROJECT_ROOT: Path = _resolve_root()


def user_data_dir(app_name: str = "fade") -> Path:
    r"""
    Returns a per-user data directory that is writable even when the app is
    installed to a read-only location (e.g. Program Files).

    Windows : %APPDATA%\<app_name>   e.g. C:\Users\Alice\AppData\Roaming\fade
    macOS   : ~/Library/Application Support/<app_name>
    Linux   : ~/.local/share/<app_name>   (XDG_DATA_HOME respected)
    """
    if sys.platform == "win32":
        base = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support"
    else:
        base = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))
    d = base / app_name
    d.mkdir(parents=True, exist_ok=True)
    return d
