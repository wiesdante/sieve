"""Named, saved lists (e.g. several blacklists) as plain data."""

from __future__ import annotations

DEFAULT_NAME = "Default"


class PresetLists:
    """Plain data: list name -> text, plus which one is selected."""

    def __init__(self, lists: dict[str, str] | None = None, current: str | None = None) -> None:
        self.lists: dict[str, str] = dict(lists) if lists else {DEFAULT_NAME: ""}
        self.current = current if current in self.lists else next(iter(self.lists))

    @classmethod
    def from_data(cls, data) -> PresetLists:
        """Accepts the saved form ({"current", "lists"}) or a bare string (older versions)."""
        if isinstance(data, str):
            return cls({DEFAULT_NAME: data})
        if isinstance(data, dict) and isinstance(data.get("lists"), dict):
            lists = {str(k): v for k, v in data["lists"].items() if isinstance(v, str)}
            if lists:
                return cls(lists, data.get("current"))
        return cls()

    def to_data(self) -> dict:
        return {"current": self.current, "lists": dict(self.lists)}

    @property
    def text(self) -> str:
        return self.lists[self.current]

    def unique_name(self, base: str) -> str:
        name, number = base, 2
        while name in self.lists:
            name = f"{base} {number}"
            number += 1
        return name
