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

    def proxy_pool(self) -> ProxyPool | None:
        """The configured proxy pool, or ``None`` if proxies are turned off."""
        if not self.settings.proxy_enabled:
            return None
        proxies, _ = parse_proxy_list(self.settings.proxies)
        if not proxies:
            return None
        return ProxyPool(proxies, self.settings.proxy_rotation)
