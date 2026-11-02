"""Proxy parsing, rotation and health checks shared by all tools.

Accepted input formats (one per line)::

    host:port
    host:port:user:password
    user:password@host:port
    http://user:password@host:port
    socks5://host:port
"""

from __future__ import annotations

import itertools
import random
import threading
import time
from dataclasses import dataclass
from urllib.parse import quote, unquote, urlsplit

import requests

SUPPORTED_SCHEMES = ("http", "https", "socks4", "socks5", "socks5h")
ROTATION_MODES = {"round_robin": "Round-robin", "random": "Random"}
IP_ECHO_URL = "https://api.ipify.org?format=json"


class ProxyParseError(ValueError):
    pass


@dataclass(frozen=True)
class Proxy:
    scheme: str
    host: str
    port: int
    username: str = ""
    password: str = ""

    @property
    def address(self) -> str:
        return f"{self.host}:{self.port}"

    @property
    def url(self) -> str:
        auth = ""
        if self.username:
            auth = quote(self.username, safe="")
            if self.password:
                auth += ":" + quote(self.password, safe="")
            auth += "@"
        return f"{self.scheme}://{auth}{self.host}:{self.port}"

    def for_requests(self) -> dict[str, str]:
        return {"http": self.url, "https": self.url}

    def for_playwright(self) -> dict[str, str]:
        config = {"server": f"{self.scheme}://{self.host}:{self.port}"}
        if self.username:
            config["username"] = self.username
            config["password"] = self.password
        return config

    def __str__(self) -> str:
        return f"{self.scheme}://{self.address}"


def _port(value: str, line: str) -> int:
    try:
        port = int(value)
    except ValueError:
        raise ProxyParseError(f"Invalid port: {line}") from None
    if not 0 < port < 65536:
        raise ProxyParseError(f"Invalid port: {line}")
    return port


def parse_proxy(line: str, default_scheme: str = "http") -> Proxy:
    text = line.strip()
    if not text:
        raise ProxyParseError("Empty line")

    if "://" in text:
        parts = urlsplit(text)
        scheme = parts.scheme.lower()
        if scheme not in SUPPORTED_SCHEMES:
            raise ProxyParseError(f"Unsupported protocol: {line}")
        if not parts.hostname or parts.port is None:
            raise ProxyParseError(f"Missing host or port: {line}")
        return Proxy(
            scheme, parts.hostname, parts.port,
            unquote(parts.username or ""), unquote(parts.password or ""),
        )

    if "@" in text:
        credentials, _, address = text.rpartition("@")
        username, _, password = credentials.partition(":")
        host, sep, port = address.rpartition(":")
        if not sep or not host:
            raise ProxyParseError(f"Missing host or port: {line}")
        return Proxy(default_scheme, host, _port(port, line), username, password)

    pieces = text.split(":")
    if len(pieces) == 2:
        return Proxy(default_scheme, pieces[0], _port(pieces[1], line))
    if len(pieces) >= 4:
        password = ":".join(pieces[3:])
        return Proxy(default_scheme, pieces[0], _port(pieces[1], line), pieces[2], password)
    raise ProxyParseError(f"Unrecognized format: {line}")


def parse_proxy_list(lines: list[str]) -> tuple[list[Proxy], list[str]]:
    """Parse many lines, skipping blanks and ``#`` comments. Returns (proxies, errors)."""
    proxies: list[Proxy] = []
    errors: list[str] = []
    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        try:
            proxies.append(parse_proxy(stripped))
        except ProxyParseError as exc:
            errors.append(str(exc))
    return proxies, errors


class ProxyPool:
    """Thread-safe proxy rotation."""

    def __init__(self, proxies: list[Proxy], mode: str = "round_robin") -> None:
        if mode not in ROTATION_MODES:
            raise ValueError(f"Unknown rotation mode: {mode}")
        self._proxies = list(proxies)
        self._mode = mode
        self._cycle = itertools.cycle(self._proxies) if self._proxies else None
        self._lock = threading.Lock()

    def __len__(self) -> int:
        return len(self._proxies)

    def next(self) -> Proxy | None:
        if not self._proxies:
            return None
        with self._lock:
            if self._mode == "random":
                return random.choice(self._proxies)
            return next(self._cycle)


@dataclass(frozen=True)
class ProxyCheckResult:
    proxy: Proxy
    ok: bool
    ip: str = ""
    latency_ms: int = 0
    error: str = ""


def check_proxy(proxy: Proxy, timeout: float = 10.0) -> ProxyCheckResult:
    started = time.perf_counter()
    try:
        response = requests.get(IP_ECHO_URL, proxies=proxy.for_requests(), timeout=timeout)
        response.raise_for_status()
        ip = response.json().get("ip", "")
    except Exception as exc:
        return ProxyCheckResult(proxy, False, error=_short_error(exc))
    latency = int((time.perf_counter() - started) * 1000)
    return ProxyCheckResult(proxy, True, ip=ip, latency_ms=latency)


def _short_error(exc: Exception) -> str:
    if isinstance(exc, requests.exceptions.ProxyError):
        return "Proxy refused the connection"
    if isinstance(exc, requests.exceptions.ConnectTimeout | requests.exceptions.ReadTimeout):
        return "Timed out"
    if isinstance(exc, requests.exceptions.InvalidSchema):
        return "SOCKS support is missing"
    text = str(exc) or exc.__class__.__name__
    return text if len(text) <= 120 else text[:117] + "..."
