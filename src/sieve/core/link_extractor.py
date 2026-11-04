"""Find web links or email addresses in PDF files and plain text.

Two sources are combined for PDFs, page by page:

* **Clickable links** (link annotations): exact, even when the visible text
  differs. In email mode these are ``mailto:`` links.
* **What is written in the text**: ``https://...``, ``www.example.com`` and,
  optionally, bare domains such as ``example.com``; or email addresses.

Results keep the order in which they were first seen. Duplicate links are
detected ignoring the scheme, a leading ``www.``, letter case in the host and a
trailing slash, so ``http://www.Example.com/`` and ``https://example.com`` count
as one. Duplicate email addresses are detected ignoring letter case.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import unquote, urlsplit

LINK = "link"
TEXT = "text"

LINKS = "links"
EMAILS = "emails"
MODES = (LINKS, EMAILS)

_PROGRESS_STEP = 1

# Hosts: unicode letters and digits, labels joined by dots, ending in a TLD.
_URL = re.compile(
    r"""
    (?P<url>
      (?:
        (?P<scheme>https?://)                       # a scheme may follow anything
      | (?<![\w@.\-/])(?P<www>www\.)?              # otherwise: not inside a word, path or email
      )
      (?P<host>(?:[^\W_](?:[\w-]{0,61}[^\W_])?\.)+(?P<tld>[^\W\d_]{2,63}))
      (?::\d{2,5})?
      (?P<rest>[/?\#](?:(?!https?://)[^\s<>"'\[\]{}|\\^`])*)?
    )
    """,
    re.IGNORECASE | re.VERBOSE,
)
_EMAIL = re.compile(
    r"(?<![\w.%+\-])(?P<email>[\w.%+\-]+@(?:[^\W_](?:[\w-]{0,61}[^\W_])?\.)+(?P<tld>[^\W\d_]{2,63}))(?![\w\-])"
)
_TRAILING = ".,;:!?'\""

def _words(text: str) -> list[str]:
    return text.split()


# Bare domains (no scheme, no www.) are easy to confuse with file names and with
# sentences that lack a space after the full stop, so they need a real TLD.
_COMMON_TLDS = frozenset(_words("""
    com net org info biz name pro mobi asia tel travel jobs aero coop museum edu gov mil int
    io co ai app dev me tv xyz online site store shop tech cloud blog news live club agency
    digital media space website world email page link top icu vip art design studio network
    solutions services group global company center life today academy systems software
    """))
_FILE_EXTENSIONS = frozenset(_words("""
    pdf png jpg jpeg gif svg webp bmp tif tiff ico doc docx xls xlsx ppt pptx csv txt rtf
    zip rar gz tar exe msi dll js ts css json xml yml yaml ini cfg log mp3 mp4 mov avi mkv
    wav html htm php py java jar
    """))


class ExtractCancelledError(Exception):
    pass


class PdfBackendMissingError(RuntimeError):
    pass


@dataclass(frozen=True)
class ExtractOptions:
    #: LINKS or EMAILS.
    mode: str = LINKS
    #: Links mode: also accept "example.com" without http:// or www.
    include_bare_domains: bool = True
    #: Output only the domain: the site of a link, or the part after "@" of an email.
    domains_only: bool = False

    def __post_init__(self) -> None:
        if self.mode not in MODES:
            raise ValueError(f"Unknown mode: {self.mode}")


@dataclass(frozen=True)
class Found:
    #: The link or email address (or its domain with ``domains_only``).
    value: str
    #: File name for PDFs, "Text" for pasted text.
    source: str
    #: 1-based page number, or None for pasted text.
    page: int | None
    #: LINK for clickable links (mailto: in email mode), TEXT for text matches.
    kind: str


@dataclass
class ExtractResult:
    links: list[Found]
    #: Every match found, including duplicates.
    total_found: int
    files: int = 0
    pages: int = 0
    #: (file name, error message) for files that could not be read.
    errors: list[tuple[str, str]] = field(default_factory=list)

    @property
    def lines(self) -> list[str]:
        return [item.value for item in self.links]


# --------------------------------------------------------------------- helpers
def _strip_trailing(url: str) -> str:
    while url:
        last = url[-1]
        if last in _TRAILING:
            url = url[:-1]
        elif last in ")]}" and url.count(last) > url.count({")": "(", "]": "[", "}": "{"}[last]):
            url = url[:-1]  # closing bracket that belongs to the sentence
        else:
            break
    return url


def normalize(url: str) -> str:
    """Add https:// when missing and drop trailing punctuation and slashes."""
    url = _strip_trailing(url.strip())
    if not url.lower().startswith(("http://", "https://")):
        url = "https://" + url
    return url.rstrip("/")


def domain_of(url: str) -> str:
    host = (urlsplit(url).hostname or "").lower()
    return host.removeprefix("www.")


def url_key(url: str) -> str:
    """Comparison key used to detect duplicates."""
    parts = urlsplit(url)
    host = (parts.hostname or "").lower().removeprefix("www.")
    port = f":{parts.port}" if parts.port else ""
    path = parts.path.rstrip("/")
    query = f"?{parts.query}" if parts.query else ""
    fragment = f"#{parts.fragment}" if parts.fragment else ""
    return f"{host}{port}{path}{query}{fragment}"


def _strip_email(email: str) -> str:
    return email.strip().strip(_TRAILING).rstrip(".")


def find_emails(text: str) -> list[str]:
    """Email addresses written in ``text``, in order (duplicates kept)."""
    emails = []
    for match in _EMAIL.finditer(text):
        tld = match.group("tld")
        if tld.lower() in _FILE_EXTENSIONS:  # e.g. "logo@2x.png"
            continue
        email = _strip_email(match.group("email"))
        local = email.split("@", 1)[0]
        if local and not local.startswith(".") and ".." not in local:
            emails.append(email)
    return emails


def emails_from_mailto(uri: str) -> list[str]:
    """Addresses in a ``mailto:`` link (several may be separated by commas)."""
    if not uri.lower().startswith("mailto:"):
        return []
    addresses = unquote(uri[7:].split("?", 1)[0])
    return [address for part in addresses.split(",") for address in find_emails(part)]


def _bare_domain_ok(tld: str) -> bool:
    if not tld.islower() or not tld.isascii():
        return False
    if tld in _FILE_EXTENSIONS:
        return False
    return len(tld) == 2 or tld in _COMMON_TLDS


def find_urls(text: str, include_bare_domains: bool = True) -> list[str]:
    """Links written in ``text``, normalized, in order (duplicates kept)."""
    text = _EMAIL.sub(" ", text)
    urls: list[str] = []
    for match in _URL.finditer(text):
        bare = not match.group("scheme") and not match.group("www")
        if bare and not (include_bare_domains and _bare_domain_ok(match.group("tld"))):
            continue
        url = normalize(match.group("url"))
        if domain_of(url):
            urls.append(url)
    return urls


class LinkCollector:
    """Accumulates links or emails in first-seen order, skipping duplicates."""

    def __init__(self, options: ExtractOptions | None = None) -> None:
        self._options = options or ExtractOptions()
        self._seen: set[str] = set()
        self.links: list[Found] = []
        self.total_found = 0

    def _key_and_value(self, value: str) -> tuple[str, str]:
        if self._options.mode == EMAILS:
            if self._options.domains_only:
                domain = value.rsplit("@", 1)[-1].lower()
                return domain, domain
            return value.lower(), value
        if self._options.domains_only:
            domain = domain_of(value)
            return domain, domain
        return url_key(value), value

    def add(self, value: str, source: str, page: int | None, kind: str) -> None:
        self.total_found += 1
        key, shown = self._key_and_value(value)
        if not key or key in self._seen:
            return
        self._seen.add(key)
        self.links.append(Found(shown, source, page, kind))

    def add_page(self, clickable: Iterable[str], text: str, source: str, page: int | None) -> None:
        if self._options.mode == EMAILS:
            for uri in clickable:
                for email in emails_from_mailto(uri):
                    self.add(email, source, page, LINK)
            for email in find_emails(text):
                self.add(email, source, page, TEXT)
            return

        clickable_keys: list[str] = []
        for uri in clickable:
            if uri.lower().startswith(("http://", "https://")):
                url = uri.strip().rstrip("/")
                clickable_keys.append(url_key(url))
                self.add(url, source, page, LINK)
        for url in find_urls(text, self._options.include_bare_domains):
            key = url_key(url)
            # A long link wrapped onto two lines shows up in the text cut short;
            # the clickable link on the same page already has the full address.
            if any(other != key and other.startswith(key) for other in clickable_keys):
                continue
            self.add(url, source, page, TEXT)


# ------------------------------------------------------------------- sources
def extract_from_text(text: str, options: ExtractOptions | None = None) -> ExtractResult:
    collector = LinkCollector(options)
    collector.add_page([], text, "Text", None)
    return ExtractResult(collector.links, collector.total_found)


def _pdf_module():
    try:
        import pymupdf
    except ImportError:
        try:
            import fitz as pymupdf
        except ImportError as exc:
            raise PdfBackendMissingError("PDF support (PyMuPDF) is not installed.") from exc
    return pymupdf


def ensure_pdf_backend() -> None:
    """Raise if PDFs cannot be read; used by the startup self-check."""
    _pdf_module()


def extract_from_pdfs(
    paths: list[Path],
    options: ExtractOptions | None = None,
    progress: Callable[[int, int], None] | None = None,
    cancelled: Callable[[], bool] | None = None,
) -> ExtractResult:
    pymupdf = _pdf_module()
    collector = LinkCollector(options)
    errors: list[tuple[str, str]] = []
    documents = []

    for path in paths:
        name = Path(path).name
        try:
            doc = pymupdf.open(str(path))
        except Exception as exc:
            errors.append((name, f"Could not open the file ({exc})."))
            continue
        if doc.needs_pass:
            doc.close()
            errors.append((name, "The PDF is password-protected."))
            continue
        documents.append((name, doc))

    total_pages = sum(doc.page_count for _, doc in documents)
    done = 0
    try:
        for name, doc in documents:
            for index, page in enumerate(doc, start=1):
                if cancelled and cancelled():
                    raise ExtractCancelledError
                try:
                    clickable = [link.get("uri", "") for link in page.get_links() if link.get("uri")]
                    text = page.get_text()
                except Exception as exc:
                    errors.append((name, f"Page {index} could not be read ({exc})."))
                    clickable, text = [], ""
                collector.add_page(clickable, text, name, index)
                done += 1
                if progress and done % _PROGRESS_STEP == 0:
                    progress(done, total_pages)
    finally:
        for _, doc in documents:
            doc.close()

    if progress:
        progress(total_pages, total_pages)
    return ExtractResult(
        collector.links, collector.total_found, len(documents), total_pages, errors
    )
