"""Opening pages in a real browser that is already installed on the PC.

The user's default browser is used when it can be automated (Chrome, Edge, Brave,
Vivaldi and other Chromium-based browsers); otherwise Chrome, then Edge, which
ships with Windows.

Some sites only show their content after JavaScript runs, and some answer plain
HTTP requests with a bot check that a real browser passes. ``BrowserPool`` runs a
few headless browser instances, each in its own thread (Playwright's sync API is
not thread-safe), and ``BrowserFetcher`` gives one site its own proxy and the same
``fetch`` interface as the plain HTTP fetcher.
"""

from __future__ import annotations

import contextlib
import logging
import ntpath
import queue
import re
import sys
import threading
import time
from concurrent.futures import Future
from dataclasses import dataclass

from sieve.core.email_scraper import (
    BROWSER_ALWAYS,
    BROWSER_MODES,
    BROWSER_OFF,
    BROWSER_SMART,
    FetchResult,
)

log = logging.getLogger(__name__)

OFF, SMART, ALWAYS, MODES = BROWSER_OFF, BROWSER_SMART, BROWSER_ALWAYS, BROWSER_MODES


@dataclass(frozen=True)
class BrowserChoice:
    """A browser to launch: a Playwright channel or a Chromium-based executable."""

    name: str
    channel: str | None = None
    executable: str | None = None

    @property
    def supported(self) -> bool:
        return bool(self.channel or self.executable)


CHROME = BrowserChoice("Google Chrome", channel="chrome")
EDGE = BrowserChoice("Microsoft Edge", channel="msedge")
#: Tried after the default browser; Edge ships with Windows 10/11.
FALLBACKS = (CHROME, EDGE)

# Executable name -> (display name, Playwright channel or None to launch the file itself).
_KNOWN_EXECUTABLES = {
    "chrome.exe": ("Google Chrome", "chrome"),
    "msedge.exe": ("Microsoft Edge", "msedge"),
    "brave.exe": ("Brave", None),
    "vivaldi.exe": ("Vivaldi", None),
    "chromium.exe": ("Chromium", None),
}
_UNSUPPORTED_EXECUTABLES = {
    "firefox.exe": "Firefox",
    "launcher.exe": "Opera",
    "opera.exe": "Opera",
    "safari.exe": "Safari",
}


def browser_from_command(command: str) -> BrowserChoice | None:
    """The browser behind a Windows "open" command such as
    ``"C:\\...\\chrome.exe" --single-argument %1``."""
    match = re.match(r'\s*"([^"]+)"|\s*(\S+)', command or "")
    if not match:
        return None
    path = match.group(1) or match.group(2)
    exe = ntpath.basename(path).lower()
    if exe in _KNOWN_EXECUTABLES:
        name, channel = _KNOWN_EXECUTABLES[exe]
        return BrowserChoice(name, channel=channel) if channel else BrowserChoice(name, executable=path)
    return BrowserChoice(_UNSUPPORTED_EXECUTABLES.get(exe, ntpath.splitext(ntpath.basename(path))[0]))


def default_browser() -> BrowserChoice | None:
    """The browser Windows opens web links with, or None if it cannot be read."""
    if sys.platform != "win32":
        return None
    try:
        import winreg

        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\Shell\Associations\UrlAssociations\https\UserChoice",
        ) as key:
            prog_id = winreg.QueryValueEx(key, "ProgId")[0]
        with winreg.OpenKey(winreg.HKEY_CLASSES_ROOT, rf"{prog_id}\shell\open\command") as key:
            command = winreg.QueryValueEx(key, "")[0]
    except OSError:
        return None
    return browser_from_command(command)


def launch_order(default: BrowserChoice | None) -> list[BrowserChoice]:
    """The default browser first when it can be automated, then Chrome and Edge."""
    order = [default] if default and default.supported else []
    for choice in FALLBACKS:
        if all(choice.name != item.name for item in order):
            order.append(choice)
    return order
_BLOCKED_RESOURCES = {"image", "media", "font"}
#: Longest wait for one page; a page whose scripts freeze the browser is given up after this.
PAGE_TIMEOUT = 60.0
#: Extra browsers started to replace ones stuck on a frozen page.
MAX_REPLACEMENTS = 4
_LAUNCH_ARGS = ["--disable-blink-features=AutomationControlled"]
_CHALLENGE_TITLES = ("just a moment", "attention required", "checking your browser", "please wait")


class BrowserUnavailableError(RuntimeError):
    pass


def ensure_browser_support() -> None:
    """Raise if the browser automation library is missing from the build."""
    from playwright.sync_api import sync_playwright  # noqa: F401


@dataclass
class _Job:
    url: str
    quick: bool
    proxy: dict | None
    future: Future
    #: Cookies and storage from the site's previous pages, so a passed bot check or
    #: cookie test (``?ckattempt=1``) is not repeated on every page.
    state: dict | None = None


class BrowserPool:
    """A few headless browsers shared by all sites of one run."""

    def __init__(self, size: int = 3, uses_proxies: bool = False) -> None:
        self._size = max(1, size)
        self._uses_proxies = uses_proxies
        self._jobs: queue.Queue[_Job | None] = queue.Queue()
        self._threads: list[threading.Thread] = []
        self._lock = threading.Lock()
        self._started = False
        self._closed = False
        self._replacements = 0
        self._user_agent: str | None = None
        self.error: str | None = None
        #: Name of the browser that was started, once one is running.
        self.name: str = "the browser"

    # ------------------------------------------------------------- lifecycle
    def _start(self) -> None:
        with self._lock:
            if self._started:
                return
            self._started = True
            for _ in range(self._size):
                self._add_worker()

    def _add_worker(self) -> None:
        thread = threading.Thread(target=self._worker, name=f"browser-{len(self._threads)}", daemon=True)
        thread.start()
        self._threads.append(thread)

    def _replace_stuck_worker(self) -> None:
        """A page froze its browser; start another one so the run keeps its pace."""
        with self._lock:
            if self._closed or self._replacements >= MAX_REPLACEMENTS:
                return
            self._replacements += 1
            self._add_worker()

    def close(self, wait: float = 5.0) -> None:
        """Shut the browsers down, waiting at most ``wait`` seconds in total; a browser
        stuck on a frozen page is left to end with the app."""
        with self._lock:
            if self._closed:
                return
            self._closed = True
            threads = list(self._threads)
        for _ in threads:
            self._jobs.put(None)
        deadline = time.monotonic() + wait
        for thread in threads:
            thread.join(timeout=max(0.0, deadline - time.monotonic()))

    @property
    def available(self) -> bool:
        return self.error is None

    def fetch(self, url: str, quick: bool = False, proxy: dict | None = None) -> FetchResult:
        return self.fetch_with_state(url, quick, proxy)[0]

    def fetch_with_state(
        self, url: str, quick: bool = False, proxy: dict | None = None, state: dict | None = None
    ) -> tuple[FetchResult, dict | None]:
        """Open ``url`` with the cookies in ``state``; returns the page and the new state."""
        if self._closed:
            return FetchResult(url, error="Browser was closed"), state
        if self.error:
            return FetchResult(url, error=f"Browser not available: {self.error}"), state
        self._start()
        future: Future = Future()
        self._jobs.put(_Job(url, quick, proxy, future, state))
        try:
            return future.result(timeout=PAGE_TIMEOUT)
        except TimeoutError:
            if not future.cancel():  # the page is loading and froze its browser
                self._replace_stuck_worker()
            return FetchResult(url, error="Browser timed out"), state
        except Exception as exc:  # worker failure
            return FetchResult(url, error=f"Browser error: {exc}"), state

    # ---------------------------------------------------------------- worker
    def _launch(self, playwright):
        options: dict = {"headless": True, "args": _LAUNCH_ARGS}
        if self._uses_proxies:
            # Each site sets its own proxy on its context; Chromium wants a launch-level placeholder.
            options["proxy"] = {"server": "http://per-context"}
        last_error: Exception | None = None
        default = default_browser()
        if default and not default.supported:
            log.info("Default browser %s cannot be automated; using Chrome or Edge", default.name)
        for choice in launch_order(default):
            try:
                if choice.channel:
                    browser = playwright.chromium.launch(channel=choice.channel, **options)
                else:
                    browser = playwright.chromium.launch(executable_path=choice.executable, **options)
            except Exception as exc:
                last_error = exc
                continue
            self.name = choice.name
            # Headless browsers announce themselves as "HeadlessChrome"; many bot checks block that.
            self._user_agent = _visible_user_agent(browser)
            return browser
        raise BrowserUnavailableError(
            "No supported browser could be started (Chrome, Edge, Brave or Vivaldi)"
            + (f" ({str(last_error).splitlines()[0]})" if last_error else "")
        )

    def _worker(self) -> None:
        try:
            from playwright.sync_api import sync_playwright

            playwright = sync_playwright().start()
        except Exception as exc:
            self._fail_all(f"browser support is missing ({exc})")
            return
        try:
            browser = self._launch(playwright)
        except BrowserUnavailableError as exc:
            self._fail_all(str(exc))
            playwright.stop()
            return
        try:
            while True:
                job = self._jobs.get()
                if job is None:
                    break
                if job.future.set_running_or_notify_cancel():
                    try:
                        job.future.set_result(self._load(browser, job))
                    except Exception as exc:
                        job.future.set_result((FetchResult(job.url, error=_short(exc)), job.state))
        finally:
            try:
                browser.close()
            finally:
                playwright.stop()

    def _fail_all(self, message: str) -> None:
        log.warning("Browser unavailable: %s", message)
        self.error = message
        while True:
            try:
                job = self._jobs.get_nowait()
            except queue.Empty:
                return
            if job is not None and job.future.set_running_or_notify_cancel():
                job.future.set_result(
                    (FetchResult(job.url, error=f"Browser not available: {message}"), job.state)
                )

    def _load(self, browser, job: _Job) -> tuple[FetchResult, dict | None]:
        context_options: dict = {
            "ignore_https_errors": True,
            "locale": "en-US",
            "viewport": {"width": 1366, "height": 900},
        }
        if job.proxy:
            context_options["proxy"] = job.proxy
        if self._user_agent:
            context_options["user_agent"] = self._user_agent
        if job.state:
            context_options["storage_state"] = job.state
        context = browser.new_context(**context_options)
        try:
            context.route(
                "**/*",
                lambda route: route.abort()
                if route.request.resource_type in _BLOCKED_RESOURCES
                else route.continue_(),
            )
            page = context.new_page()
            timeout = 12_000 if job.quick else 25_000
            response = page.goto(job.url, wait_until="domcontentloaded", timeout=timeout)
            status = response.status if response else 0
            _settle(page, quick=job.quick)
            # Bot checks reload the page once they pass; wait for that.
            if _is_challenge(page):
                deadline = time.monotonic() + 15
                while _is_challenge(page) and time.monotonic() < deadline:
                    page.wait_for_timeout(1000)
                if not _is_challenge(page):
                    status = 200
                    _settle(page, quick=True)
            result = FetchResult(page.url, text=page.content(), status=status)
            state = job.state
            with contextlib.suppress(Exception):
                state = context.storage_state()
            return result, state
        finally:
            context.close()


def _visible_user_agent(browser) -> str | None:
    try:
        page = browser.new_page()
        try:
            agent = page.evaluate("navigator.userAgent")
        finally:
            page.close()
    except Exception:
        return None
    return agent.replace("HeadlessChrome", "Chrome") if agent else None


def _settle(page, quick: bool) -> None:
    """Give scripts a moment to render content, without waiting forever."""
    with contextlib.suppress(Exception):
        page.wait_for_load_state("networkidle", timeout=2500 if quick else 5000)


def _is_challenge(page) -> bool:
    try:
        title = page.title().lower()
    except Exception:
        return False
    return any(marker in title for marker in _CHALLENGE_TITLES)


def _short(exc: Exception) -> str:
    text = str(exc).splitlines()[0] if str(exc) else exc.__class__.__name__
    if "ERR_NAME_NOT_RESOLVED" in text:
        return "Domain not found"
    if "Timeout" in text:
        return "Browser timed out"
    if "ERR_CONNECTION" in text or "ERR_ADDRESS" in text:
        return "Could not connect"
    return text if len(text) <= 120 else text[:117] + "..."


class BrowserFetcher:
    """One site's view of the shared browser pool, with that site's proxy."""

    def __init__(self, pool: BrowserPool, proxy: dict | None = None) -> None:
        self._pool = pool
        self._proxy = proxy
        self._state: dict | None = None

    @property
    def available(self) -> bool:
        return self._pool.available

    @property
    def name(self) -> str:
        return self._pool.name

    def fetch(self, url: str, quick: bool = False) -> FetchResult:
        result, self._state = self._pool.fetch_with_state(url, quick, self._proxy, self._state)
        return result
