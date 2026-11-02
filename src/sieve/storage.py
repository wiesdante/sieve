"""Small JSON documents for tool data that must survive restarts and updates.

Each document lives in ``%APPDATA%\\Sieve\\data\\<name>.json``. That folder is
never touched by the installer, so updating or reinstalling Sieve keeps it.
Writes are atomic (write to a temporary file, then rename), and the previous
version is kept as ``<name>.json.bak`` so a damaged file can be recovered.
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any

from sieve import paths

log = logging.getLogger(__name__)

_NAME = re.compile(r"^[a-z0-9_\-]+$")


def data_dir() -> Path:
    folder = paths.config_dir() / "data"
    folder.mkdir(parents=True, exist_ok=True)
    return folder


class JsonDocument:
    def __init__(self, name: str) -> None:
        if not _NAME.match(name):
            raise ValueError(f"Invalid document name: {name!r}")
        self.path = data_dir() / f"{name}.json"
        self._backup = self.path.with_suffix(".json.bak")

    def load(self, default: dict[str, Any] | None = None) -> dict[str, Any]:
        for candidate in (self.path, self._backup):
            try:
                data = json.loads(candidate.read_text(encoding="utf-8"))
            except FileNotFoundError:
                continue
            except (OSError, ValueError):
                log.exception("Could not read %s", candidate.name)
                continue
            if isinstance(data, dict):
                return data
        return dict(default or {})

    def save(self, data: dict[str, Any]) -> None:
        tmp = self.path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        if self.path.exists():
            self.path.replace(self._backup)
        tmp.replace(self.path)
