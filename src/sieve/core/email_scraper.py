"""Find contact email addresses on websites.

For every site the scraper:

1. opens the page that was given (falling back from https to http, and between
   ``www.`` and the bare domain, when the first attempt cannot connect),
2. recognises parked domains and bot-protection pages and stops there,
3. collects addresses from schema.org data, ``mailto:`` links, Cloudflare-protected
   addresses, the visible text, the page source and a couple of the site's own scripts,
4. in **standard** mode, keeps visiting the most promising pages within a small
   budget: links ranked by how likely they lead to contact or legal pages in the
   site's language (English, Turkish, German), pages from the sitemap, and finally
   common paths such as ``/kontakt``, ``/impressum`` or ``/iletisim``.

**Direct** mode only scans the exact URL that was given.

Downloading goes through a ``Fetcher`` so the logic can be tested without a
network and so every site can use its own proxy.
"""

from __future__ import annotations

import codecs
import heapq
import re
import threading
import time
from collections.abc import Callable
from concurrent.futures import FIRST_COMPLETED, Future, ThreadPoolExecutor, wait
from dataclasses import dataclass, field
from typing import Protocol
from urllib.parse import unquote, urljoin, urlsplit

from sieve.core.email_filter import EmailFilter, normalize_email, prepare_text
from sieve.core.link_extractor import find_emails
from sieve.core.site_discovery import (
    LANGUAGES,
    detect_languages,
    guess_urls,
    has_contact_form,
    is_blocked,
    is_parked,
    parse_sitemap,
    same_site,
    score_link,
    site_key,
    sitemaps_from_robots,
    structured_emails,
    toggle_www,
)

STANDARD = "standard"
DIRECT = "direct"
MODES = (STANDARD, DIRECT)

FOUND = "found"
EMPTY = "empty"
FAILED = "failed"
FORM_ONLY = "form_only"
PARKED = "parked"
BLOCKED = "blocked"
STATUSES = (FOUND, FORM_ONLY, EMPTY, PARKED, BLOCKED, FAILED)

MAX_BYTES = 5 * 1024 * 1024
SITE_TIME_LIMIT = 90.0
PAGE_BUDGET = 8
MAX_SCRIPTS = 2
#: A page this likely to hold contact details ends the search once it yields an address.
STRONG_PAGE = 90
#: Below this, a page is only visited while nothing has been found yet.
WEAK_PAGE = 30

_SCRIPT_HINTS = ("contact", "email", "mail", "kontakt", "iletisim", "config", "app", "main")
# Errors where another address variant (http://, www.) may work. A read timeout
# means the server was reached but is slow, so trying variants only wastes time.
_CONNECTION_ERRORS = (
    "could not connect", "connection timed out", "connection refused", "ssl",
    "domain not found", "connecttimeout", "newconnectionerror",
)
_ACCESS_DENIED = {401: "Access denied", 403: "Access denied", 451: "Unavailable for legal reasons"}
#: Where an address was found; addresses only seen in page code are treated with suspicion.
_CODE_SOURCES = ("source", "script")


class ScrapeCancelledError(Exception):
    pass


# ----------------------------------------------------------------- fetching
@dataclass(frozen=True)
class FetchResult:
    url: str
    text: str | None = None
    status: int = 0
    error: str | None = None

    @property
    def ok(self) -> bool:
        return self.text is not None and self.error is None


class Fetcher(Protocol):
    def fetch(self, url: str, quick: bool = False) -> FetchResult: ...


# ------------------------------------------------------------------- results
@dataclass(frozen=True)
class FoundEmail:
    email: str
    #: The page the address was first seen on.
    page: str
    #: How it was found: "structured", "link" (mailto), "protected" (Cloudflare),
    #: "text", "source" or "script".
    how: str


@dataclass
class SiteResult:
    site: str
    status: str = EMPTY
    final_url: str = ""
    emails: list[FoundEmail] = field(default_factory=list)
    rejected: list[tuple[str, str]] = field(default_factory=list)
    pages: int = 0
    error: str = ""
    elapsed: float = 0.0
    language: str = ""
    #: A page with a contact form that was seen (useful when no address exists).
    contact_form: str = ""
    log: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class ScrapeOptions:
    mode: str = STANDARD
    workers: int = 10
    site_time_limit: float = SITE_TIME_LIMIT
    page_budget: int = PAGE_BUDGET

    def __post_init__(self) -> None:
        if self.mode not in MODES:
            raise ValueError(f"Unknown mode: {self.mode}")


# --------------------------------------------------------------- page parsing
def decode_cloudflare(encoded: str) -> str | None:
    """Decode a Cloudflare "email protection" hex string."""
    try:
        key = int(encoded[:2], 16)
        return "".join(chr(int(encoded[i:i + 2], 16) ^ key) for i in range(2, len(encoded), 2))
    except (ValueError, IndexError):
        return None


@dataclass
class ParsedPage:
    #: (raw candidate, how) pairs, most trustworthy sources first.
    candidates: list[tuple[str, str]]
    #: Same-site links with a contact score, best first.
    links: list[tuple[int, str]]
    #: Same-site scripts that may contain addresses.
    scripts: list[str]
    languages: tuple[str, ...] = ("en",)
    visible_text: str = ""
    contact_form: bool = False


def parse_page(html: str, page_url: str, languages: tuple[str, ...] | None = None) -> ParsedPage:
    from bs4 import BeautifulSoup

    if len(html) > MAX_BYTES:
        return ParsedPage([(email, "source") for email in find_emails(html)], [], [])

    soup = BeautifulSoup(html, "html.parser")
    visible = soup.get_text(" ")
    if languages is None:
        html_tag = soup.find("html")
        languages = detect_languages(html_tag.get("lang") if html_tag else None, page_url, visible)

    candidates: list[tuple[str, str]] = [(email, "structured") for email in structured_emails(soup)]
    for tag in soup.find_all(attrs={"data-cfemail": True}):
        decoded = decode_cloudflare(str(tag.get("data-cfemail", "")))
        if decoded:
            candidates.append((decoded, "protected"))

    scored: dict[str, int] = {}
    order: list[str] = []
    for anchor in soup.find_all("a", href=True):
        href = str(anchor["href"]).strip()
        lower = href.lower()
        if lower.startswith("mailto:"):
            for part in unquote(href[7:].split("?", 1)[0]).split(","):
                candidates.append((part.strip(), "link"))
            continue
        if "/cdn-cgi/l/email-protection#" in lower:
            decoded = decode_cloudflare(href.rsplit("#", 1)[1])
            if decoded:
                candidates.append((decoded, "protected"))
            continue
        if lower.startswith(("tel:", "javascript:", "#", "whatsapp:", "sms:")):
            continue
        text = anchor.get_text(" ", strip=True) or str(anchor.get("title", "")) or str(anchor.get("aria-label", ""))
        # Links are ranked with every supported language: many sites mix them.
        score = score_link(href, text, LANGUAGES)
        if score <= 0:
            continue
        target = urljoin(page_url, href).split("#", 1)[0]
        if not target.lower().startswith(("http://", "https://")) or not same_site(target, page_url):
            continue
        if target.rstrip("/") == page_url.rstrip("/"):
            continue
        if target not in scored:
            order.append(target)
        scored[target] = max(score, scored.get(target, 0))

    candidates += [(email, "text") for email in find_emails(visible)]
    # Text written backwards and flipped with CSS (direction: rtl) to hide it from bots.
    for email in find_emails(visible[::-1]):
        if same_site("https://" + email.rsplit("@", 1)[-1], page_url):
            candidates.append((email, "decoded"))
    candidates += [(email, "source") for email in find_emails(html)]

    scripts: list[str] = []
    for script in soup.find_all("script", src=True):
        src = str(script["src"])
        target = urljoin(page_url, src)
        wanted = any(hint in src.lower() for hint in _SCRIPT_HINTS)
        if wanted and same_site(target, page_url) and target not in scripts:
            scripts.append(target)

    links = sorted(((scored[url], url) for url in order), key=lambda item: -item[0])
    return ParsedPage(candidates, links, scripts, languages, visible, has_contact_form(soup))


def normalize_site(line: str) -> str | None:
    text = line.strip()
    if not text or text.startswith("#"):
        return None
    if any(ch.isspace() for ch in text):
        return None
    if not re.match(r"^https?://", text, re.IGNORECASE):
        text = "https://" + text
    host = urlsplit(text).hostname or ""
    return text if "." in host else None


def parse_sites(text: str) -> list[str]:
    """One site per line; blank lines, comments and repeats are skipped."""
    seen: set[str] = set()
    sites: list[str] = []
    for line in text.splitlines():
        site = normalize_site(line)
        if not site:
            continue
        parts = urlsplit(site)
        key = (parts.hostname or "").lower().removeprefix("www.") + parts.path.rstrip("/")
        if key not in seen:
            seen.add(key)
            sites.append(site)
    return sites


# ------------------------------------------------------------- site scanning
class _SiteScan:
    def __init__(
        self,
        site: str,
        fetcher: Fetcher,
        email_filter: EmailFilter | None,
        options: ScrapeOptions,
        cancelled: Callable[[], bool] | None,
    ) -> None:
        self.result = SiteResult(site)
        self._fetcher = fetcher
        self._filter = email_filter
        self._options = options
        self._cancelled = cancelled
        self._started = time.monotonic()
        self._seen: set[str] = set()
        self._rejected_seen: set[str] = set()
        self._visited: set[str] = set()
        self._queue: list[tuple[int, int, str, str]] = []
        self._counter = 0

    # -- helpers
    def log(self, level: str, message: str) -> None:
        self.result.log.append(f"[{time.strftime('%H:%M:%S')}] {level:<7} {message}")

    def _out_of_time(self) -> bool:
        if self._cancelled and self._cancelled():
            return True
        return time.monotonic() - self._started > self._options.site_time_limit

    def _budget_left(self) -> bool:
        return self.result.pages < self._options.page_budget

    def _fetch(self, url: str, quick: bool = False) -> FetchResult:
        self.result.pages += 1
        self._visited.add(url.rstrip("/"))
        return self._fetcher.fetch(url, quick=quick)

    def _reject(self, email: str, reason: str) -> None:
        if email not in self._rejected_seen:
            self._rejected_seen.add(email)
            self.result.rejected.append((email, reason))

    def _site_key(self) -> str:
        return site_key(self.result.final_url or self.result.site)

    def _decode_obfuscated(self, candidates: list[tuple[str, str]]) -> list[tuple[str, str]]:
        """Undo ROT13 and reversed-text tricks some sites use to hide addresses.

        A decoded address is only trusted if it belongs to the site itself (or, for
        ROT13 once the page is known to use it, if its username is the site's name).
        """
        own = self._site_key()
        own_name = own.split(".")[0]
        decoded: list[tuple[str, str]] = []
        uses_rot13 = False
        for raw, _how in candidates:
            email = normalize_email(raw)
            if email and site_key(email.split("@", 1)[1]) != own:
                rot = normalize_email(codecs.encode(email, "rot13"))
                if rot and site_key(rot.split("@", 1)[1]) == own:
                    uses_rot13 = True
        for raw, how in candidates:
            email = normalize_email(raw)
            if not email or site_key(email.split("@", 1)[1]) == own:
                decoded.append((raw, how))
                continue
            rot = normalize_email(codecs.encode(email, "rot13")) if uses_rot13 else None
            rev = normalize_email(email[::-1])
            if rot and (site_key(rot.split("@", 1)[1]) == own or rot.split("@", 1)[0] == own_name):
                decoded.append((rot, "decoded"))
            elif rev and site_key(rev.split("@", 1)[1]) == own:
                decoded.append((rev, "decoded"))
            else:
                decoded.append((raw, how))
        return decoded

    def _collect(self, candidates: list[tuple[str, str]], page: str) -> int:
        added = 0
        own = self._site_key()
        for raw, how in self._decode_obfuscated(candidates):
            if how in _CODE_SOURCES:
                email = normalize_email(raw)
                if email and site_key(email.split("@", 1)[1]) != own:
                    # e.g. a JavaScript library author's address in a code comment
                    self._reject(email, "Only in page code, other domain")
                    continue
            if self._filter is not None:
                verdict = self._filter.judge(raw)
                if verdict is None:
                    continue
                if not verdict.ok:
                    self._reject(verdict.email, verdict.reason or "")
                    continue
                email = verdict.email
            else:
                email = normalize_email(raw)
                if email is None:
                    continue
            if email not in self._seen:
                self._seen.add(email)
                self.result.emails.append(FoundEmail(email, page, how))
                self.log("FOUND", f"{email} ({how})")
                added += 1
        return added

    def _enqueue(self, url: str, score: int, why: str) -> None:
        if url.rstrip("/") in self._visited:
            return
        self._counter += 1
        heapq.heappush(self._queue, (-score, self._counter, url, why))

    def _scan_scripts(self, parsed: ParsedPage, page_url: str) -> None:
        for script_url in parsed.scripts[:MAX_SCRIPTS]:
            if self._out_of_time() or not self._budget_left():
                return
            script = self._fetch(script_url, quick=True)
            if script.ok:
                found = find_emails(prepare_text(script.text or ""))
                self._collect([(email, "script") for email in found], page_url)

    # -- main flow
    def _open_first_page(self) -> tuple[FetchResult, str]:
        site = self.result.site
        attempts = [site]
        if site.lower().startswith("https://"):
            attempts.append("http://" + site[8:])
        attempts.append(toggle_www(site))
        last = FetchResult(site, error="No response")
        for index, url in enumerate(attempts):
            if index:
                self.log("WARN", f"{last.error}; trying {url}")
            last = self._fetch(url)
            if last.ok or not _is_connection_error(last.error):
                return last, url
        return last, attempts[-1]

    def run(self) -> SiteResult:
        self.log("INFO", f"Scanning {self.result.site}")
        home, _ = self._open_first_page()
        if not home.ok:
            self.result.status = FAILED
            self.result.error = home.error or "No response"
            self.log("ERROR", self.result.error)
            return self._finish()

        self.result.final_url = home.url
        html = home.text or ""
        if is_blocked(home.status, html) or home.status in _ACCESS_DENIED:
            self.result.status = BLOCKED
            self.result.error = (
                f"Bot protection or captcha (HTTP {home.status})" if is_blocked(home.status, html)
                else f"{_ACCESS_DENIED[home.status]} (HTTP {home.status})"
            )
            self.log("WARN", self.result.error)
            return self._finish()
        if home.status >= 400:
            self.result.status = FAILED
            self.result.error = f"The site answered HTTP {home.status}"
            self.log("ERROR", self.result.error)
            return self._finish()

        parsed = parse_page(html, home.url)
        self.result.language = parsed.languages[0]
        self.log("OK", f"Connected: {home.url} (HTTP {home.status}, language: {self.result.language})")
        if is_parked(home.url, parsed.visible_text):
            self.result.status = PARKED
            self.result.error = "Parked or for-sale domain"
            self.log("WARN", self.result.error)
            return self._finish()

        self._collect(parsed.candidates, home.url)
        if parsed.contact_form:
            self.result.contact_form = home.url
        self._scan_scripts(parsed, home.url)

        if self._options.mode == STANDARD:
            for score, url in parsed.links:
                self._enqueue(url, score, "link")
            self._crawl(home.url, parsed.languages)

        self._decide_status()
        return self._finish()

    def _crawl(self, home_url: str, languages: tuple[str, ...]) -> None:
        sitemap_checked = False
        guessed = False
        while not self._out_of_time() and self._budget_left():
            best = -self._queue[0][0] if self._queue else 0
            if self.result.emails and best < STRONG_PAGE:
                return  # found addresses and nothing clearly better is left
            if not self.result.emails and best < STRONG_PAGE and not sitemap_checked:
                sitemap_checked = True
                self._read_sitemap(home_url, languages)
                continue
            if not self._queue:
                if self.result.emails or guessed:
                    return
                guessed = True
                for url in guess_urls(home_url, languages):
                    self._enqueue(url, WEAK_PAGE, "guess")
                continue
            neg_score, _, url, why = heapq.heappop(self._queue)
            score = -neg_score
            if url.rstrip("/") in self._visited or (self.result.emails and score < STRONG_PAGE):
                continue
            if self._visit(url, score, why, home_url, languages) and score >= STRONG_PAGE:
                return

    def _visit(self, url: str, score: int, why: str, home_url: str, languages: tuple[str, ...]) -> bool:
        page = self._fetch(url, quick=why == "guess")
        if not page.ok:
            if why != "guess":
                self.log("WARN", f"Could not open {url} ({page.error})")
            return False
        # Unknown paths often answer 404 or redirect to the home page.
        if page.status >= 400 or page.url.rstrip("/") == home_url.rstrip("/"):
            return False
        self.log("INFO", f"Visited {page.url} ({why}, score {score})")
        parsed = parse_page(page.text or "", page.url, languages)
        added = self._collect(parsed.candidates, page.url)
        if parsed.contact_form and not self.result.contact_form:
            self.result.contact_form = page.url
        for link_score, link in parsed.links[:10]:
            if link_score >= WEAK_PAGE:
                self._enqueue(link, link_score, "link")
        return added > 0

    def _read_sitemap(self, home_url: str, languages: tuple[str, ...]) -> None:
        parts = urlsplit(home_url)
        root = f"{parts.scheme}://{parts.netloc}"
        robots = self._fetch(urljoin(root, "/robots.txt"), quick=True)
        sitemaps = sitemaps_from_robots(robots.text or "") if robots.ok and robots.status < 400 else []
        if not sitemaps:
            sitemaps = [urljoin(root, "/sitemap.xml")]
        pages: list[str] = []
        for sitemap_url in sitemaps[:2]:
            if not self._budget_left() or self._out_of_time():
                break
            sitemap = self._fetch(sitemap_url, quick=True)
            if not sitemap.ok or sitemap.status >= 400:
                continue
            found, children = parse_sitemap(sitemap.text or "")
            pages += found
            for child in children[:1]:
                if self._budget_left():
                    child_map = self._fetch(child, quick=True)
                    if child_map.ok and child_map.status < 400:
                        pages += parse_sitemap(child_map.text or "")[0]
        added = 0
        for url in pages[:5000]:
            if not same_site(url, home_url):
                continue
            score = score_link(url, "", LANGUAGES)
            if score >= 40:
                self._enqueue(url, score, "sitemap")
                added += 1
        self.log("INFO", f"Sitemap: {len(pages)} pages, {added} look like contact pages")

    def _decide_status(self) -> None:
        if self.result.emails:
            self.result.status = FOUND
        elif self.result.contact_form:
            self.result.status = FORM_ONLY
            self.result.error = f"Only a contact form ({self.result.contact_form})"
        else:
            self.result.status = EMPTY

    def _finish(self) -> SiteResult:
        self.result.elapsed = time.monotonic() - self._started
        self.log("DONE", f"{len(self.result.emails)} emails, {self.result.pages} requests, "
                         f"{self.result.elapsed:.1f}s")
        return self.result


def _is_connection_error(error: str | None) -> bool:
    text = (error or "").lower()
    if not text or "read timed out" in text or "readtimeout" in text:
        return False
    return any(word in text for word in _CONNECTION_ERRORS)


def scan_site(
    site: str,
    fetcher: Fetcher,
    email_filter: EmailFilter | None = None,
    options: ScrapeOptions | None = None,
    cancelled: Callable[[], bool] | None = None,
) -> SiteResult:
    scan = _SiteScan(site, fetcher, email_filter, options or ScrapeOptions(), cancelled)
    try:
        return scan.run()
    except Exception as exc:  # never let one site stop the whole run
        scan.result.status = FAILED
        scan.result.error = f"Unexpected error: {exc}"
        scan.log("ERROR", scan.result.error)
        return scan._finish()


# ------------------------------------------------------------------ the run
@dataclass
class ScrapeSummary:
    results: list[SiteResult] = field(default_factory=list)
    stopped: bool = False

    def count(self, status: str) -> int:
        return sum(1 for result in self.results if result.status == status)


def scrape_sites(
    sites: list[str],
    fetcher_for: Callable[[int], Fetcher],
    email_filter: EmailFilter | None = None,
    options: ScrapeOptions | None = None,
    progress: Callable[[SiteResult, int], None] | None = None,
    cancelled: Callable[[], bool] | None = None,
) -> ScrapeSummary:
    """Scan ``sites`` in parallel; ``progress`` is called with each finished site."""
    options = options or ScrapeOptions()
    summary = ScrapeSummary()
    lock = threading.Lock()
    workers = max(1, min(options.workers, len(sites) or 1))
    queue = list(enumerate(sites))
    queue.reverse()

    with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="scrape") as pool:
        running: set[Future] = set()

        def submit_next() -> None:
            index, site = queue.pop()
            running.add(
                pool.submit(scan_site, site, fetcher_for(index), email_filter, options, cancelled)
            )

        while queue and len(running) < workers:
            submit_next()
        while running:
            done, _ = wait(running, timeout=0.5, return_when=FIRST_COMPLETED)
            for future in done:
                running.discard(future)
                result = future.result()
                with lock:
                    summary.results.append(result)
                if progress:
                    progress(result, len(sites))
            if cancelled and cancelled():
                summary.stopped = True
                queue.clear()
            while queue and len(running) < workers:
                submit_next()
    return summary


# ------------------------------------------------------------ HTTP fetching
class HttpFetcher:
    """Downloads pages with requests; one instance per site (one session, one proxy)."""

    HEADERS = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36"
        ),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9,tr;q=0.8",
    }
    TEXT_TYPES = ("text", "html", "json", "xml", "javascript")

    def __init__(self, proxies: dict[str, str] | None = None) -> None:
        import requests
        import urllib3
        from requests.adapters import HTTPAdapter
        from urllib3.util.retry import Retry

        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
        self._requests = requests
        self._session = requests.Session()
        self._session.headers.update(self.HEADERS)
        retry = Retry(total=1, backoff_factor=0.2, status_forcelist=[500, 502, 503, 504],
                      allowed_methods=["GET"])
        adapter = HTTPAdapter(max_retries=retry)
        self._session.mount("https://", adapter)
        self._session.mount("http://", adapter)
        if proxies:
            self._session.proxies.update(proxies)

    def fetch(self, url: str, quick: bool = False) -> FetchResult:
        timeout = (3, 5) if quick else (5, 10)
        max_seconds = 8 if quick else 15
        try:
            # Many small business sites have broken certificates; contacts are still worth finding.
            response = self._session.get(url, timeout=timeout, verify=False, stream=True)
        except self._requests.RequestException as exc:
            return FetchResult(url, error=_short(exc))
        with response:
            content_type = response.headers.get("Content-Type", "").lower()
            if content_type and not any(kind in content_type for kind in self.TEXT_TYPES):
                return FetchResult(response.url, status=response.status_code,
                                   error=f"Not a web page ({content_type.split(';')[0]})")
            body = bytearray()
            started = time.monotonic()
            try:
                for chunk in response.iter_content(chunk_size=16384):
                    body.extend(chunk)
                    if len(body) > MAX_BYTES or time.monotonic() - started > max_seconds:
                        break
            except self._requests.RequestException as exc:
                if not body:
                    return FetchResult(response.url, status=response.status_code, error=_short(exc))
            encoding = response.encoding if "charset" in content_type else "utf-8"
            text = bytes(body).decode(encoding or "utf-8", errors="replace")
            return FetchResult(response.url, text=text, status=response.status_code)


def _short(exc: Exception) -> str:
    text = str(exc)
    for marker, label in (
        ("SSLError", "SSL error"),
        ("NameResolutionError", "Domain not found"),
        ("getaddrinfo failed", "Domain not found"),
        ("ConnectTimeout", "Connection timed out"),
        ("ReadTimeout", "Read timed out"),
        ("ProxyError", "Proxy error"),
        ("TooManyRedirects", "Too many redirects"),
        ("ConnectionRefused", "Connection refused"),
        ("NewConnectionError", "Could not connect"),
    ):
        if marker in text or marker == exc.__class__.__name__:
            return label
    return text if len(text) <= 120 else text[:117] + "..."
