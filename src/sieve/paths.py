"""Filesystem locations used by the application.

On Windows, user settings live in ``%APPDATA%\\Sieve`` and machine-local data
(logs, downloaded updates) in ``%LOCALAPPDATA%\\Sieve``. Setting the
``SIEVE_HOME`` environment variable redirects everything to a single folder,
which is used by the test suite.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from sieve import APP_ID


def _root(env_var: str, fallback: str) -> Path:
    override = os.environ.get("SIEVE_HOME")
    if override:
        return Path(override)
    base = os.environ.get(env_var)
    return (Path(base) if base else Path.home() / fallback) / APP_ID


def _ensure(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def config_dir() -> Path:
    """Roaming folder for settings and stored credentials."""
    return _ensure(_root("APPDATA", ".config"))


def data_dir() -> Path:
    """Machine-local folder for logs, caches and downloads."""
    return _ensure(_root("LOCALAPPDATA", ".local/share"))


def logs_dir() -> Path:
    return _ensure(data_dir() / "logs")


def updates_dir() -> Path:
    return _ensure(data_dir() / "updates")


def is_frozen() -> bool:
    """True when running from the packaged executable."""
    return bool(getattr(sys, "frozen", False))


def resource_path(*parts: str) -> Path:
    """Path to a bundled resource (``assets/...``), in source or frozen mode."""
    base = getattr(sys, "_MEIPASS", None)
    root = Path(base) if base else Path(__file__).resolve().parents[2]
    return root.joinpath(*parts)
