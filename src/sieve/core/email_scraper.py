"""Find contact email addresses on websites.

For every site the scraper:

1. downloads the page that was given (falling back from https to http when the
   secure connection fails),
2. collects addresses from the raw HTML, the visible text, ``mailto:`` links,
   Cloudflare-protected addresses and a couple of the site's own scripts,
3. in **standard** mode, also visits the two pages that look most like a
   contact page, and if nothing was found yet, tries common paths such as
   ``/contact`` and ``/iletisim``.

**Direct** mode only scans the exact URL that was given.

Downloading is done through a ``Fetcher`` so the logic can be tested without
a network and so every site can use its own proxy.
"""

from __future__ import annotations

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

STANDARD = "standard"
DIRECT = "direct"
MODES = (STANDARD, DIRECT)

FOUND = "found"
EMPTY = "empty"
FAILED = "failed"

MAX_BYTES = 5 * 1024 * 1024
SITE_TIME_LIMIT = 90.0
MAX_CONTACT_PAGES = 2
MAX_SCRIPTS = 2

COMMON_PATHS = (
    "/iletisim",
    "/contact",
    "/contact-us",
    "/bize-ulasin",
    "/about",
    "/hakkimizda",
)
_EXACT_CONTACT_TEXTS = {
    "contact", "contact us", "iletisim", "iletişim", "bize ulaşın", "bize ulasin",
    "iletisim bilgileri", "iletişim bilgileri", "kontakt",
}
_CONTACT_ENDINGS = (
    "contact", "contact-us", "iletisim", "iletişim", "bize-ulasin", "iletisim.html",
    "contact.html", "kontakt",
)
_CONTACT_WORD = re.compile(r"\b(contact(?:[- ]us)?|iletisim|iletişim|bize[- ]ula[sş][ıi]n|kontakt)\b")
_SECONDARY_WORD = re.compile(r"\b(about(?:[- ]us)?|hakk[ıi]m[ıi]zda|support|impressum|künye)\b")
_NEGATIVE_WORD = re.compile(
    r"\b(product|products|urun|kategori|category|item|detail|blog|article|news|haber|connector|termini)\b"
)
_SCRIPT_HINTS = ("contact", "email", "app", "main", "config")
_CONNECTION_ERRORS = ("connect", "ssl", "timed out", "timeout", "max retries")


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
    #: How it was found: "text", "link" (mailto), "protected" (Cloudflare) or "script".
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
    log: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class ScrapeOptions:
    mode: str = STANDARD
    workers: int = 10
    site_time_limit: float = SITE_TIME_LIMIT

    def __post_init__(self) -> None:
        if self.mode not in MODES:
            raise ValueError(f"Unknown mode: {self.mode}")


# --------------------------------------------------------------- page parsing
def _same_site(a: str, b: str) -> bool:
    host_a = (urlsplit(a).hostname or "").lower().removeprefix("www.")
    host_b = (urlsplit(b).hostname or "").lower().removeprefix("www.")
    return bool(host_a) and host_a == host_b


def decode_cloudflare(encoded: str) -> str | None:
    """Decode a Cloudflare "email protection" hex string."""
    try:
        key = int(encoded[:2], 16)
        return "".join(chr(int(encoded[i:i + 2], 16) ^ key) for i in range(2, len(encoded), 2))
    except (ValueError, IndexError):
        return None


@dataclass
class ParsedPage:
    #: (raw candidate, how) pairs in the order found.
    candidates: list[tuple[str, str]]
    #: Links that look like contact pages, best first.
    contact_links: list[str]
    #: Same-site scripts that may contain addresses.
    scripts: list[str]


def parse_page(html: str, page_url: str) -> ParsedPage:
    from bs4 import BeautifulSoup

    candidates: list[tuple[str, str]] = [(email, "text") for email in find_emails(html)]
    contact_scored: list[tuple[int, int, str]] = []
    scripts: list[str] = []
    if len(html) > MAX_BYTES:
        return ParsedPage(candidates, [], [])

    soup = BeautifulSoup(html, "html.parser")
    for email in find_emails(soup.get_text(" ")):
        candidates.append((email, "text"))

    for tag in soup.find_all(attrs={"data-cfemail": True}):
        decoded = decode_cloudflare(str(tag.get("data-cfemail", "")))
        if decoded:
            candidates.append((decoded, "protected"))

    for order, anchor in enumerate(soup.find_all("a", href=True)):
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
        score = _contact_score(lower, anchor.get_text(" ", strip=True).lower())
        if score > 0:
            target = urljoin(page_url, href).split("#", 1)[0]
            if _same_site(target, page_url):
                contact_scored.append((-score, order, target))

    contact_links: list[str] = []
    for _, _, target in sorted(contact_scored):
        if target not in contact_links and target.rstrip("/") != page_url.rstrip("/"):
            contact_links.append(target)

    for script in soup.find_all("script", src=True):
        src = str(script["src"])
        target = urljoin(page_url, src)
        wanted = any(hint in src.lower() for hint in _SCRIPT_HINTS)
        if wanted and _same_site(target, page_url) and target not in scripts:
            scripts.append(target)

    return ParsedPage(candidates, contact_links, scripts)


def _contact_score(href: str, text: str) -> int:
    score = 0
    if text in _EXACT_CONTACT_TEXTS:
        score += 50
    path = href.split("?", 1)[0].strip("/")
    if path.endswith(_CONTACT_ENDINGS):
        score += 50
    if _CONTACT_WORD.search(href):
        score += 10
    if _CONTACT_WORD.search(text):
        score += 10
    if _SECONDARY_WORD.search(href):
        score += 5
    if _SECONDARY_WORD.search(text):
        score += 5
    if _NEGATIVE_WORD.search(href):
        score -= 30
    return score


def guess_urls(final_url: str) -> list[str]:
    """Common contact paths at the site root and, if the site redirected into a
    sub-folder such as /tr/, inside that folder too."""
    parts = urlsplit(final_url)
    root = f"{parts.scheme}://{parts.netloc}"
    folder = final_url if final_url.endswith("/") else final_url.rsplit("/", 1)[0] + "/"
    urls: list[str] = []
    for path in COMMON_PATHS:
        candidates = [urljoin(root, path)]
        if parts.path.strip("/"):
            candidates.append(urljoin(folder, path.lstrip("/")))
        for url in candidates:
            if url not in urls:
                urls.append(url)
    return urls


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

    def log(self, level: str, message: str) -> None:
        self.result.log.append(f"[{time.strftime('%H:%M:%S')}] {level:<7} {message}")

    def _out_of_time(self) -> bool:
        if self._cancelled and self._cancelled():
            return True
        return time.monotonic() - self._started > self._options.site_time_limit

    def _fetch(self, url: str, quick: bool = False) -> FetchResult:
        self.result.pages += 1
        return self._fetcher.fetch(url, quick=quick)

    def _collect(self, candidates: list[tuple[str, str]], page: str, source: str) -> int:
        added = 0
        for raw, how in candidates:
            if self._filter is not None:
                verdict = self._filter.judge(raw)
                if verdict is None:
                    continue
                if not verdict.ok:
                    if verdict.email not in self._rejected_seen:
                        self._rejected_seen.add(verdict.email)
                        self.result.rejected.append((verdict.email, verdict.reason or ""))
                    continue
                email = verdict.email
            else:
                email = normalize_email(raw)
                if email is None:
                    continue
            if email not in self._seen:
                self._seen.add(email)
                self.result.emails.append(FoundEmail(email, page, how))
                self.log("FOUND", f"{email} ({source})")
                added += 1
        return added

    def _scan(self, url: str, source: str, quick: bool = False) -> tuple[FetchResult, ParsedPage | None]:
        page = self._fetch(url, quick=quick)
        if not page.ok:
            return page, None
        parsed = parse_page(page.text or "", page.url)
        self._collect(parsed.candidates, page.url, source)
        for script_url in parsed.scripts[:MAX_SCRIPTS]:
            if self._out_of_time():
                break
            script = self._fetch(script_url, quick=True)
            if script.ok:
                self._collect(
                    [(email, "script") for email in find_emails(prepare_text(script.text or ""))],
                    page.url,
                    "script",
                )
        return page, parsed

    def run(self) -> SiteResult:
        site = self.result.site
        self.log("INFO", f"Scanning {site}")
        home, parsed = self._scan(site, "first page")
        if not home.ok and site.lower().startswith("https://") and _is_connection_error(home.error):
            self.log("WARN", f"HTTPS failed ({home.error}), trying HTTP")
            home, parsed = self._scan("http://" + site[8:], "first page")

        if not home.ok:
            self.result.status = FAILED
            self.result.error = home.error or "No response"
            self.log("ERROR", self.result.error)
            return self._finish()

        self.result.final_url = home.url
        self.log("OK", f"Connected: {home.url}")
        if not self.result.emails:
            self.log("INFO", "No emails on the first page")

        if self._options.mode == STANDARD and parsed is not None:
            for link in parsed.contact_links[:MAX_CONTACT_PAGES]:
                if self._out_of_time():
                    break
                self.log("INFO", f"Contact page: {link}")
                page, _ = self._scan(link, "contact page")
                if not page.ok:
                    self.log("WARN", f"Could not open {link} ({page.error})")

            if not self.result.emails:
                self._guess(home.url)

        self.result.status = FOUND if self.result.emails else EMPTY
        return self._finish()

    def _guess(self, final_url: str) -> None:
        self.log("INFO", "Trying common contact paths")
        home_key = final_url.rstrip("/")
        for url in guess_urls(final_url):
            if self._out_of_time():
                self.log("WARN", "Time limit reached")
                return
            page = self._fetch(url, quick=True)
            # Many sites answer unknown paths by redirecting to the home page.
            if not page.ok or page.status != 200 or page.url.rstrip("/") == home_key:
                continue
            self.log("INFO", f"Found page: {page.url}")
            parsed = parse_page(page.text or "", page.url)
            if self._collect(parsed.candidates, page.url, "guessed page"):
                return
        self.log("INFO", "No emails found on common paths")

    def _finish(self) -> SiteResult:
        self.result.elapsed = time.monotonic() - self._started
        self.log("DONE", f"{len(self.result.emails)} emails in {self.result.elapsed:.1f}s")
        return self.result


def _is_connection_error(error: str | None) -> bool:
    return bool(error) and any(word in error.lower() for word in _CONNECTION_ERRORS)


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
