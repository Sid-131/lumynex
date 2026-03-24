"""
Path resolver — handles both running from source and as a PyInstaller bundle.

When frozen (exe):
  - Read-only assets (styles.qss, defaults.json) live in sys._MEIPASS
  - Writable data (user_settings.json, logs/) live next to the exe

When running from source:
  - Everything lives under the project root
"""
import os
import sys
from pathlib import Path


def _is_frozen() -> bool:
    return getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS")


def bundle_dir() -> Path:
    """
    Directory containing read-only bundled assets (styles.qss, defaults.json).
    Points to sys._MEIPASS when frozen, project root when running from source.
    """
    if _is_frozen():
        return Path(sys._MEIPASS)
    return Path(__file__).resolve().parent.parent


def data_dir() -> Path:
    """
    Directory for user-writable files (settings, event log, logs/).
    Next to the .exe when frozen, project root when running from source.
    Guaranteed to exist.
    """
    if _is_frozen():
        d = Path(sys.executable).parent
    else:
        d = Path(__file__).resolve().parent.parent
    d.mkdir(parents=True, exist_ok=True)
    return d
