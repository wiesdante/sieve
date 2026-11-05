"""Collect the links on a list of pages.

Typical use: open directory, exhibitor or search-result pages and collect the
company websites they link to, ready for Email Scraper.

For every page in the list the collector:

1. opens it with a plain request, or in the browser when the page is blocked,
   built with JavaScript or shows no links (Smart), or always (Always),
2. collects every ``<a href>`` with its text, made absolute and tidied
   (no ``#fragment``, optionally no tracking parameters such as ``utm_source``),
3. keeps the links that pass the filters: which sites (all, other sites, the same
   site), social/share/app-store links, file downloads and your own exclude rules,
4. optionally follows "next page" links (``rel="next"``, "Next", "Sonraki",
   "Weiter", "»"...) to read the following pages of a paginated list.

Requests to the same site are spaced out, and a site that blocks is given a longer
pause and one more try, in the browser when available.
"""

from __future__ import annotations

import re
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from http import HTTPStatus
from urllib.parse import parse_qsl, urlencode, urljoin, urlsplit, urlunsplit

from sieve.core.email_scraper import (
    BROWSER_ALWAYS,
    BROWSER_OFF,
    BROWSER_SMART,
    FetchResult,
    looks_js_rendered,
)
from sieve.core.parallel import run_parallel
from sieve.core.site_discovery import fold, is_blocked, site_key

# ------------------------------------------------------------------- options
ALL = "all"
EXTERNAL = "external"
INTERNAL = "internal"
SCOPES = (ALL, EXTERNAL, INTERNAL)

#: Results for one page in the list.
READ = "read"
NO_LINKS = "no_links"
BLOCKED = "blocked"
FAILED = "failed"
STATUSES = (READ, NO_LINKS, BLOCKED, FAILED)

PAGE_CHOICES = (1, 5, 10, 20, 50, 100)
#: Gap between two requests to the same site, and after it blocked us.
HOST_INTERVAL = 1.0
HOST_PENALTY = 6.0
#: A list page still loading after this long (per page to read) is given up.
SECONDS_PER_PAGE = 120.0
_KNOWN_STATUSES = frozenset(int(status) for status in HTTPStatus)
_ACCESS_DENIED = {401, 403, 429, 451}

# ------------------------------------------------------------------ built-ins
#: Social networks, share buttons, messengers, app stores and maps.
SOCIAL_HOSTS = frozenset({
    "facebook.com", "fb.com", "fb.me", "messenger.com", "twitter.com", "x.com", "t.co",
    "linkedin.com", "lnkd.in", "instagram.com", "threads.net", "youtube.com", "youtu.be",
    "tiktok.com", "pinterest.com", "pin.it", "reddit.com", "tumblr.com", "snapchat.com",
    "vk.com", "ok.ru", "telegram.me", "t.me", "wa.me", "whatsapp.com", "line.me",
    "weibo.com", "discord.gg", "discord.com", "flickr.com", "vimeo.com", "dailymotion.com",
    "addtoany.com", "sharethis.com", "addthis.com", "xing.com", "bsky.app", "mastodon.social",
    "apps.apple.com", "itunes.apple.com", "play.google.com", "maps.google.com",
    "maps.app.goo.gl", "goo.gl", "wechat.com", "qq.com",
})
#: Google Maps lives under google.<tld>/maps.
_MAPS_PATH = re.compile(r"^/maps(?:/|$)")
_FILE_EXTENSIONS = re.compile(
    r"\.(?:pdf|docx?|xlsx?|pptx?|odt|ods|csv|txt|rtf|zip|rar|7z|gz|tar|exe|msi|dmg|apk|"
    r"jpe?g|png|gif|webp|svg|bmp|ico|tiff?|mp[34]|m4a|wav|avi|mov|wmv|webm|css|js|xml|json)$",
    re.IGNORECASE,
)
#: Query parameters that only track where a click came from.
_TRACKING_PREFIXES = ("utm_", "mc_", "pk_", "hsa_", "_hs")
_TRACKING_PARAMS = frozenset({
    "fbclid", "gclid", "dclid", "gbraid", "wbraid", "msclkid", "yclid", "twclid", "ttclid",
    "igshid", "_ga", "_gl", "ref_src", "mkt_tok", "srsltid", "spm", "scid",
})
_SKIP_SCHEMES = ("javascript:", "mailto:", "tel:", "sms:", "data:", "about:", "callto:", "skype:", "whatsapp:")

# "Next page" link texts in the languages the scraper knows (compared after folding).
_NEXT_WORDS = (
    "next", "next page", "next ›", "next »", "next >", "›", "»", ">", "→", "older",
    "sonraki", "sonraki sayfa", "ileri", "weiter", "nachste", "nachste seite", "vor",
    "suivant", "page suivante", "siguiente", "successivo", "successiva", "avanti",
    "proximo", "proxima", "seguinte", "volgende", "nastepna", "dalsi", "kovetkezo",
    "urmatoarea", "sledeca", "naslednja", "kitas", "nakamais", "jargmine", "nasta", "neste",
    "naeste", "seuraava", "следующая", "далее", "вперед", "επομενη", "הבא", "التالي",
    "tiep", "berikutnya", "selanjutnya", "다음", "次へ", "次", "下一页", "下页",
)
_NEXT_TEXTS = frozenset(fold(word) for word in _NEXT_WORDS)
_ARROWS = re.compile(r"[›»>→⟶⇒▶►▸❯〉]+")
_NEXT_CLASS = re.compile(r"(?:^|[-_\s])next(?:$|[-_\s])", re.IGNORECASE)


@dataclass
class LinkFilterSettings:
    """Which of the collected links are kept. Saved between sessions."""

    scope: str = ALL
    #: Reduce every link to its site's home page, one per site (ready for Email Scraper).
    home_pages_only: bool = False
    skip_social: bool = True
    skip_files: bool = True
    strip_tracking: bool = True
    #: Links containing any of these (letter case ignored) are dropped.
    exclude: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "scope": self.scope, "home_pages_only": self.home_pages_only,
            "skip_social": self.skip_social, "skip_files": self.skip_files,
            "strip_tracking": self.strip_tracking,
        }

    @classmethod
    def from_dict(cls, data: dict) -> LinkFilterSettings:
        scope = data.get("scope", ALL)
        return cls(
            scope=scope if scope in SCOPES else ALL,
            home_pages_only=bool(data.get("home_pages_only", False)),
            skip_social=bool(data.get("skip_social", True)),
            skip_files=bool(data.get("skip_files", True)),
            strip_tracking=bool(data.get("strip_tracking", True)),
        )


def parse_rules(text: str) -> list[str]:
    """Exclude rules from the editor: one per line, blank lines and ``# notes`` ignored."""
    rules: list[str] = []
    for line in (text or "").splitlines():
        rule = line.strip()
        if rule and not rule.startswith("#") and rule.lower() not in rules:
            rules.append(rule.lower())
    return rules


@dataclass
class CollectOptions:
    filters: LinkFilterSettings = field(default_factory=LinkFilterSettings)
    workers: int = 5
    browser: str = BROWSER_SMART
    #: Pages read per list entry: 1 reads only the page itself, more follows "next" links.
    max_pages: int = 1
    host_interval: float = HOST_INTERVAL
    host_penalty: float = HOST_PENALTY


# -------------------------------------------------------------------- results
@dataclass
class Link:
    url: str
    text: str
    page: str


@dataclass
class PageResult:
    """The outcome for one entry of the list (with the pages that followed it)."""

    url: str
    status: str = READ
    final_url: str = ""
    pages: int = 0
    #: Links that passed the filters on these pages (not yet compared with other entries).
    links: list[Link] = field(default_factory=list)
    #: (link, reason) for links the filters dropped.
    rejected: list[tuple[str, str]] = field(default_factory=list)
    total_links: int = 0
    error: str = ""
    via: str = "http"
    elapsed: float = 0.0
    log: list[str] = field(default_factory=list)


@dataclass
class CollectSummary:
    results: list[PageResult] = field(default_factory=list)
    stopped: bool = False


# ---------------------------------------------------------------- link tidying
def clean_url(url: str, strip_tracking: bool = True) -> str:
    """Lower-case the host, drop the ``#fragment`` and, optionally, tracking parameters."""
    parts = urlsplit(url.strip())
    query = parts.query
    if strip_tracking and query:
        pairs = [
            (key, value) for key, value in parse_qsl(query, keep_blank_values=True)
            if not (key.lower() in _TRACKING_PARAMS or key.lower().startswith(_TRACKING_PREFIXES))
        ]
        query = urlencode(pairs, doseq=True)
    path = parts.path or "/"
    return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), path, query, ""))


def link_key(url: str) -> str:
    """Two links with the same key are the same page (scheme, ``www.`` and a trailing slash
    do not count)."""
    parts = urlsplit(url)
    host = (parts.hostname or "").lower().removeprefix("www.")
    path = parts.path.rstrip("/") or "/"
    return f"{host}{path}" + (f"?{parts.query}" if parts.query else "")


def home_page(url: str) -> str:
    parts = urlsplit(url)
    return f"{parts.scheme}://{parts.netloc}/"


def _host_matches(host: str, domains: frozenset[str]) -> bool:
    host = host.removeprefix("www.")
    return any(host == domain or host.endswith("." + domain) for domain in domains)


def is_social(url: str) -> bool:
    parts = urlsplit(url)
    host = (parts.hostname or "").lower()
    if _host_matches(host, SOCIAL_HOSTS):
        return True
    return bool(re.match(r"^(?:www\.)?google\.[a-z.]+$", host) and _MAPS_PATH.match(parts.path))


def is_file(url: str) -> bool:
    return bool(_FILE_EXTENSIONS.search(urlsplit(url).path))


class LinkFilter:
    def __init__(self, settings: LinkFilterSettings) -> None:
        self.settings = settings

    def judge(self, url: str, page_url: str) -> str | None:
        """Why the link is dropped, or None to keep it."""
        settings = self.settings
        if settings.scope != ALL:
            same = site_key(url) == site_key(page_url)
            if settings.scope == EXTERNAL and same:
                return "Same site"
            if settings.scope == INTERNAL and not same:
                return "Other site"
        if settings.skip_social and is_social(url):
            return "Social, share or app link"
        if settings.skip_files and not settings.home_pages_only and is_file(url):
            return "File download"
        lowered = url.lower()
        for rule in settings.exclude:
            if rule in lowered:
                return f"Exclude rule: {rule}"
        return None


# ---------------------------------------------------------------- page parsing
@dataclass
class ParsedLinks:
    links: list[tuple[str, str]]
    next_page: str | None
    visible_text: str


def _anchor_text(anchor) -> str:
    text = " ".join(anchor.get_text(" ", strip=True).split())
    if not text:
        text = anchor.get("aria-label") or anchor.get("title") or ""
        if not text:
            image = anchor.find("img")
            text = (image.get("alt") or "") if image else ""
    text = " ".join(str(text).split())
    return text if len(text) <= 120 else text[:117] + "..."


def parse_links(html: str, page_url: str) -> ParsedLinks:
    """Every link on the page, made absolute, with its text; plus the next page, if any."""
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html or "", "html.parser")
    base = page_url
    base_tag = soup.find("base", href=True)
    if base_tag:
        base = urljoin(page_url, base_tag["href"])
    links: list[tuple[str, str]] = []
    for anchor in soup.find_all(["a", "area"], href=True):
        href = anchor["href"].strip()
        if not href or href.startswith("#") or href.lower().startswith(_SKIP_SCHEMES):
            continue
        url = urljoin(base, href)
        if urlsplit(url).scheme not in ("http", "https"):
            continue
        links.append((url, _anchor_text(anchor)))
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()
    return ParsedLinks(links, find_next_page(soup, page_url, base), soup.get_text(" ", strip=True))


def find_next_page(soup, page_url: str, base: str | None = None) -> str | None:
    """The "next page" link of a paginated list, on the same site."""
    base = base or page_url
    current = link_key(page_url)
    candidates: list[str] = []
    for tag in soup.find_all(["link", "a"], href=True):
        rel = [value.lower() for value in (tag.get("rel") or [])]
        if "next" in rel:
            candidates.insert(0, tag["href"])
    for anchor in soup.find_all("a", href=True):
        label = fold(" ".join(anchor.get_text(" ", strip=True).split()))
        aria = fold(anchor.get("aria-label") or anchor.get("title") or "")
        bare = _ARROWS.sub("", label).strip()  # "Next →", "› Next" -> "next"
        classes = " ".join(anchor.get("class") or [])
        if (
            label in _NEXT_TEXTS
            or (bare and bare in _NEXT_TEXTS)
            or aria in _NEXT_TEXTS
            or aria.startswith(("next", "go to next"))
            or (_NEXT_CLASS.search(classes) and len(label) <= 20)
        ):
            candidates.append(anchor["href"])
    for href in candidates:
        if not href or href.startswith("#") or href.lower().startswith(_SKIP_SCHEMES):
            continue
        url = urljoin(base, href)
        same_site = urlsplit(url).scheme in ("http", "https") and site_key(url) == site_key(page_url)
        if same_site and link_key(url) != current:
            return url
    return None


# ------------------------------------------------------------------ throttling
class HostThrottle:
    """Spaces out requests to the same host; a host that blocked us waits longer."""

    def __init__(self, interval: float = HOST_INTERVAL, penalty: float = HOST_PENALTY) -> None:
        self._interval = interval
        self._penalty = penalty
        self._next: dict[str, float] = {}
        self._penalized: set[str] = set()
        self._lock = threading.Lock()

    def wait(self, host: str, cancelled: Callable[[], bool] | None = None) -> None:
        with self._lock:
            now = time.monotonic()
            gap = self._penalty if host in self._penalized else self._interval
            slot = max(now, self._next.get(host, 0.0))
            self._next[host] = slot + gap
        while True:
            remaining = slot - time.monotonic()
            if remaining <= 0 or (cancelled and cancelled()):
                return
            time.sleep(min(remaining, 0.25))

    def penalize(self, host: str) -> None:
        with self._lock:
            self._penalized.add(host)
            self._next[host] = max(self._next.get(host, 0.0), time.monotonic() + self._penalty)

    def is_penalized(self, host: str) -> bool:
        return host in self._penalized


# ----------------------------------------------------------------- one entry
class _Fetcher:  # the same small interface as Email Scraper's fetchers
    def fetch(self, url: str, quick: bool = False) -> FetchResult: ...


def _short_status(result: FetchResult, html: str) -> tuple[str, str] | None:
    """(status, reason) when the answer is not a usable page."""
    if not result.ok:
        return FAILED, result.error or "No response"
    if result.status not in _KNOWN_STATUSES:
        return BLOCKED, f"Unusual answer (HTTP {result.status}), likely bot protection"
    if is_blocked(result.status, html):
        return BLOCKED, f"Bot protection or captcha (HTTP {result.status})"
    if result.status in _ACCESS_DENIED:
        return BLOCKED, f"Access denied (HTTP {result.status})"
    if result.status >= 400:
        return FAILED, f"The page answered HTTP {result.status}"
    return None


def _worth_a_browser(problem: tuple[str, str] | None, parsed: ParsedLinks | None, html: str) -> bool:
    if problem is not None:
        status, reason = problem
        lowered = reason.lower()
        if status == FAILED:
            return not any(word in lowered for word in ("domain not found", "refused", "http 404", "http 410"))
        return True
    if parsed is None:
        return False
    # Very little text next to scripts: the list is probably drawn by JavaScript.
    thin = len(parsed.visible_text) < 400 and "<script" in html.lower()
    return not parsed.links or thin or looks_js_rendered(html, parsed.visible_text)


class _EntryRun:
    """Reads one entry of the list and the pages that follow it."""

    def __init__(
        self,
        url: str,
        fetcher: _Fetcher,
        browser: _Fetcher | None,
        options: CollectOptions,
        link_filter: LinkFilter,
        throttle: HostThrottle,
        cancelled: Callable[[], bool] | None,
    ) -> None:
        self.result = PageResult(url)
        self._fetcher = fetcher
        self._browser = browser if options.browser != BROWSER_OFF else None
        self._options = options
        self._filter = link_filter
        self._throttle = throttle
        self._cancelled = cancelled
        self._started = time.monotonic()
        self._seen: set[str] = set()
        self._rejected_seen: set[str] = set()
        self._used_browser = False
        self._used_plain = False

    def log(self, level: str, message: str) -> None:
        self.result.log.append(f"[{time.strftime('%H:%M:%S')}] {level:<7} {message}")

    def _stopped(self) -> bool:
        return bool(self._cancelled and self._cancelled())

    def _get(self, fetcher: _Fetcher, url: str) -> FetchResult:
        host = (urlsplit(url).hostname or "").lower()
        self._throttle.wait(host, self._cancelled)
        self.result.pages += 1
        return fetcher.fetch(url)

    def _open(self, url: str) -> tuple[FetchResult, ParsedLinks | None, tuple[str, str] | None]:
        """Open one page, trying the browser when Smart mode calls for it, and once more
        after a pause when the site blocks."""
        host = (urlsplit(url).hostname or "").lower()
        browser_name = getattr(self._browser, "name", "the browser")
        use_browser_first = self._browser is not None and (
            self._options.browser == BROWSER_ALWAYS or self._used_browser
        )
        fetcher = self._browser if use_browser_first else self._fetcher
        result = self._get(fetcher, url)
        if fetcher is self._browser and (result.error or "").startswith("Browser not available"):
            self.log("WARN", f"{result.error}; using plain requests")
            self._browser = None
            fetcher = self._fetcher
            use_browser_first = False
            result = self._get(fetcher, url)
        self._mark(fetcher)
        html = result.text or ""
        problem = _short_status(result, html)
        parsed = parse_links(html, result.url) if problem is None else None

        if (
            not use_browser_first
            and self._browser is not None
            and self._options.browser == BROWSER_SMART
            and _worth_a_browser(problem, parsed, html)
            and not self._stopped()
        ):
            why = problem[1] if problem else ("no links" if parsed and not parsed.links else "built with JavaScript")
            self.log("INFO", f"{why}; opening in {browser_name}")
            second = self._get(self._browser, url)
            second_html = second.text or ""
            second_problem = _short_status(second, second_html)
            second_parsed = parse_links(second_html, second.url) if second_problem is None else None
            if (second.error or "").startswith("Browser not available"):
                self.log("WARN", second.error)
                self._browser = None
            elif second_problem is None and (
                problem is not None or len(second_parsed.links) > len(parsed.links if parsed else [])
            ):
                self._mark(self._browser)
                self._used_browser = True  # keep using it for the following pages
                return second, second_parsed, None

        if problem and problem[0] == BLOCKED and not self._stopped():
            self._throttle.penalize(host)
            retry_with = self._browser or self._fetcher
            self.log("WARN", f"{problem[1]}; waiting {self._options.host_penalty:.0f}s and trying once more")
            again = self._get(retry_with, url)
            again_html = again.text or ""
            again_problem = _short_status(again, again_html)
            if again_problem is None:
                self._mark(retry_with)
                return again, parse_links(again_html, again.url), None
        return result, parsed, problem

    def _mark(self, fetcher: _Fetcher) -> None:
        if fetcher is self._browser and fetcher is not None:
            self._used_browser = True
        else:
            self._used_plain = True

    def run(self) -> PageResult:
        url = self.result.url
        self.log("INFO", f"Reading {url}")
        visited: set[str] = set()
        current: str | None = url
        while current and self.result.pages < self._options.max_pages * 3 and not self._stopped():
            page_number = len(visited) + 1
            if page_number > self._options.max_pages:
                break
            visited.add(link_key(current))
            fetched, parsed, problem = self._open(current)
            if problem:
                if page_number == 1:
                    self.result.status, self.result.error = problem
                    self.log("ERROR" if problem[0] == FAILED else "WARN", problem[1])
                else:
                    self.log("WARN", f"Stopped following pages: {problem[1]} at {current}")
                break
            if page_number == 1:
                self.result.final_url = fetched.url
            kept = self._take_links(parsed, fetched.url)
            self.log("OK", f"Page {page_number}: {fetched.url} · {len(parsed.links)} links, {kept} kept")
            next_page = parsed.next_page
            if next_page and link_key(next_page) in visited:
                next_page = None
            if next_page and page_number < self._options.max_pages:
                self.log("INFO", f"Next page: {next_page}")
            current = next_page

        if self.result.status == READ and not self.result.links:
            self.result.status = NO_LINKS
            if not self.result.error:
                self.result.error = (
                    "No links passed the filters" if self.result.total_links else "No links on the page"
                )
        self.result.via = (
            "both" if self._used_browser and self._used_plain else "browser" if self._used_browser else "http"
        )
        self.result.elapsed = time.monotonic() - self._started
        self.log("DONE", f"{len(self.result.links)} links kept, {self.result.pages} requests, "
                         f"{self.result.elapsed:.1f}s")
        return self.result

    def _take_links(self, parsed: ParsedLinks, page_url: str) -> int:
        settings = self._filter.settings
        page_key = link_key(page_url)
        next_key = link_key(clean_url(parsed.next_page, settings.strip_tracking)) if parsed.next_page else None
        kept = 0
        for raw, text in parsed.links:
            self.result.total_links += 1
            url = clean_url(raw, settings.strip_tracking)
            if link_key(url) == page_key:
                continue  # a link to the page itself
            if link_key(url) == next_key:
                continue  # the list's own "next page" link
            reason = self._filter.judge(url, page_url)
            if reason:
                if url not in self._rejected_seen:
                    self._rejected_seen.add(url)
                    self.result.rejected.append((url, reason))
                continue
            if settings.home_pages_only:
                url = home_page(url)
                key = site_key(url)
            else:
                key = link_key(url)
            if key in self._seen:
                continue
            self._seen.add(key)
            self.result.links.append(Link(url, text, page_url))
            kept += 1
        return kept


def entry_key(url: str, home_pages_only: bool) -> str:
    """The key used to tell whether two kept links are the same."""
    return site_key(url) if home_pages_only else link_key(url)


def parse_pages(text: str) -> list[str]:
    """Page addresses from the editor: one per line, ``https://`` added when missing,
    duplicates removed."""
    pages: list[str] = []
    seen: set[str] = set()
    for line in (text or "").splitlines():
        url = line.strip().strip("\"'<>")
        if not url or url.startswith("#"):
            continue
        if "://" not in url:
            url = "https://" + url
        if urlsplit(url).scheme not in ("http", "https") or not urlsplit(url).hostname:
            continue
        key = link_key(url)
        if key not in seen:
            seen.add(key)
            pages.append(url)
    return pages


# ----------------------------------------------------------------- the run
def collect_links(
    pages: list[str],
    fetcher_for: Callable[[int], _Fetcher],
    options: CollectOptions | None = None,
    progress: Callable[[PageResult, int], None] | None = None,
    cancelled: Callable[[], bool] | None = None,
    browser_for: Callable[[int], _Fetcher | None] | None = None,
) -> CollectSummary:
    """Read ``pages`` in parallel; ``progress`` is called with each finished entry."""
    options = options or CollectOptions()
    summary = CollectSummary()
    link_filter = LinkFilter(options.filters)
    throttle = HostThrottle(options.host_interval, options.host_penalty)
    lock = threading.Lock()

    def work(index: int, url: str) -> PageResult:
        with lock:  # the factories may share state, such as a rotating proxy pool
            fetcher = fetcher_for(index)
            browser = browser_for(index) if browser_for and options.browser != BROWSER_OFF else None
        return _EntryRun(url, fetcher, browser, options, link_filter, throttle, cancelled).run()

    def report(_index: int, result: PageResult) -> None:
        summary.results.append(result)
        if progress:
            progress(result, len(pages))

    def give_up(_index: int, url: str, seconds: float) -> PageResult:
        stamp = time.strftime("%H:%M:%S")
        return PageResult(
            url, FAILED, error=f"Gave up after {int(seconds)}s (page did not respond)", elapsed=seconds,
            log=[f"[{stamp}] ERROR   Gave up: the page was still loading after {int(seconds)}s"],
        )

    def on_error(_index: int, url: str, exc: Exception) -> PageResult:
        return PageResult(url, FAILED, error=f"Unexpected error: {exc}")

    summary.stopped = run_parallel(
        pages, work, options.workers, report, cancelled,
        hard_limit=SECONDS_PER_PAGE * max(1, options.max_pages) + 60,
        give_up=give_up, on_error=on_error,
    )
    return summary
