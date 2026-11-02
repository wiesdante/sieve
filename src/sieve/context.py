"""Shared services handed to every tool."""

from __future__ import annotations

from dataclasses import dataclass, field

from sieve.credentials import CredentialStore
from sieve.proxy import ProxyPool, parse_proxy_list
from sieve.settings import Settings


@dataclass
class AppContext:
    settings: Settings = field(default_factory=Settings.load)
    credentials: CredentialStore = field(default_factory=CredentialStore)

    def save_settings(self) -> None:
        self.settings.save()

    def tool_settings(self, tool_id: str) -> dict:
        """Mutable preferences dict for one tool; call ``save_settings`` after changing it."""
        stored = self.settings.tool_settings.get(tool_id)
        if not isinstance(stored, dict):
            stored = self.settings.tool_settings[tool_id] = {}
        return stored

    def proxy_pool(self) -> ProxyPool | None:
        """The configured proxy pool, or ``None`` if proxies are turned off."""
        if not self.settings.proxy_enabled:
            return None
        proxies, _ = parse_proxy_list(self.settings.proxies)
        if not proxies:
            return None
        return ProxyPool(proxies, self.settings.proxy_rotation)
