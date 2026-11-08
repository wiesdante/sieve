"""Persistent, non-secret user settings stored as JSON."""

from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path
from typing import Any

from sieve import paths

log = logging.getLogger(__name__)


def default_path() -> Path:
    return paths.config_dir() / "settings.json"


@dataclass
class Settings:
    check_updates_on_startup: bool = True
    skipped_version: str = ""
    proxy_enabled: bool = False
    proxy_rotation: str = "round_robin"
    proxies: list[str] = field(default_factory=list)
    window_geometry: str = ""
    #: This computer's activation code (see sieve.core.licensing).
    activation_code: str = ""
    #: Per-tool preferences, keyed by ``Tool.id``.
    tool_settings: dict[str, dict] = field(default_factory=dict)

    @classmethod
    def load(cls, path: Path | None = None) -> Settings:
        path = path or default_path()
        try:
            raw: Any = json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return cls()
        except (OSError, ValueError):
            log.exception("Settings file is unreadable, falling back to defaults")
            return cls()
        if not isinstance(raw, dict):
            return cls()

        defaults = cls()
        values: dict[str, Any] = {}
        for f in fields(cls):
            if f.name not in raw:
                continue
            value = raw[f.name]
            expected = type(getattr(defaults, f.name))
            if isinstance(value, expected):
                values[f.name] = value
            else:
                log.warning("Ignoring setting %r with unexpected type", f.name)
        return cls(**values)

    def save(self, path: Path | None = None) -> None:
        path = path or default_path()
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(asdict(self), indent=2, ensure_ascii=False), encoding="utf-8")
        tmp.replace(path)
