import threading

import pytest

from sieve.core.email_filter import EmailFilter
from sieve.core.email_scraper import (
    DIRECT,
    EMPTY,
    FAILED,
    FOUND,
    FetchResult,
    ScrapeOptions,
    decode_cloudflare,
    guess_urls,
    parse_page,
    parse_sites,
    scan_site,
    scrape_sites,
)

pytest.importorskip("bs4")


def cf_encode(email: str, key: int = 0x42) -> str:
    return f"{key:02x}" + "".join(f"{ord(ch) ^ key:02x}" for ch in email)


class FakeFetcher:
    """Serves pages from a dict; unknown URLs return 404 or redirect home."""

    def __init__(self, pages, fail=(), redirect_unknown_to=None):
        self.pages = pages
        self.fail = dict(fail)
        self.redirect_unknown_to = redirect_unknown_to
        self.requested = []

    def fetch(self, url, quick=False):
        self.requested.append(url)
        if url in self.fail:
            return FetchResult(url, error=self.fail[url])
        if url in self.pages:
            return FetchResult(url, text=self.pages[url], status=200)
        if self.redirect_unknown_to:
            target = self.redirect_unknown_to
            return FetchResult(target, text=self.pages[target], status=200)
        return FetchResult(url, text="Not found", status=404)


def test_cloudflare_decoding():
    assert decode_cloudflare(cf_encode("info@acme.com")) == "info@acme.com"
    assert decode_cloudflare("zz") is None


def test_parse_page_finds_every_kind_of_address():
    html = f"""
    <html><body>
      <p>Write to sales@acme.com</p>
      <a href="mailto:Support@Acme.com?subject=Hi">Mail us</a>
      <span class="__cf_email__" data-cfemail="{cf_encode('hidden@acme.com')}">[email protected]</span>
      <a href="/cdn-cgi/l/email-protection#{cf_encode('cf2@acme.com')}">mail</a>
      <a href="/products/contact-lens">Lenses</a>
      <a href="/iletisim">İletişim</a>
      <a href="/about-us">About us</a>
      <a href="https://other.com/contact">Partner</a>
      <script src="/js/contact-form.js"></script>
      <script src="https://cdn.other.com/main.js"></script>
    </body></html>
    """
    parsed = parse_page(html, "https://acme.com/")
    found = {raw.lower() for raw, _ in parsed.candidates}
    assert {"sales@acme.com", "support@acme.com", "hidden@acme.com", "cf2@acme.com"} <= found
    urls = [url for _, url in parsed.links]
    assert urls[:2] == ["https://acme.com/iletisim", "https://acme.com/about-us"]
    assert "https://other.com/contact" not in urls
    assert parsed.scripts == ["https://acme.com/js/contact-form.js"]


def test_standard_mode_visits_contact_page_and_filters_junk():
    fetcher = FakeFetcher({
        "https://acme.com": '<a href="/contact">Contact</a> noreply@acme.com',
        "https://acme.com/contact": "Mail: info@acme.com, x@o1.ingest.sentry.io",
    })
    result = scan_site("https://acme.com", fetcher, EmailFilter())
    assert result.status == FOUND
    assert [found.email for found in result.emails] == ["info@acme.com"]
    assert result.emails[0].page == "https://acme.com/contact"
    assert {email for email, _ in result.rejected} == {"noreply@acme.com", "x@o1.ingest.sentry.io"}


def test_direct_mode_does_not_follow_links():
    fetcher = FakeFetcher({
        "https://acme.com/team": '<a href="/contact">Contact</a>',
        "https://acme.com/contact": "info@acme.com",
    })
    result = scan_site("https://acme.com/team", fetcher, options=ScrapeOptions(mode=DIRECT))
    assert result.status == EMPTY
    assert fetcher.requested == ["https://acme.com/team"]


def test_guessing_skips_redirects_to_home_and_stops_at_first_hit():
    fetcher = FakeFetcher({
        "https://acme.com": "Welcome",
        "https://acme.com/contact": "info@acme.com",
        "https://acme.com/about": "other@acme.com",
    })
    result = scan_site("https://acme.com", fetcher)
    assert [found.email for found in result.emails] == ["info@acme.com"]
    assert "https://acme.com/about" not in fetcher.requested

    soft404 = FakeFetcher({"https://acme.com": "Welcome info@nowhere.io"}, redirect_unknown_to="https://acme.com")
    assert scan_site("https://acme.com", soft404).emails[0].email == "info@nowhere.io"


def test_https_failure_falls_back_to_http():
    fetcher = FakeFetcher({"http://old.com": "info@old.com"}, fail={"https://old.com": "SSL error"})
    result = scan_site("https://old.com", fetcher)
    assert result.status == FOUND
    assert result.final_url == "http://old.com"


def test_unreachable_site_is_failed():
    fetcher = FakeFetcher({}, fail={
        "https://gone.com": "Domain not found",
        "http://gone.com": "Domain not found",
        "https://www.gone.com": "Domain not found",
    })
    result = scan_site("https://gone.com", fetcher)
    assert result.status == FAILED
    assert result.error == "Domain not found"
    assert fetcher.requested == ["https://gone.com", "http://gone.com", "https://www.gone.com"]


def test_guess_urls_include_language_folder():
    urls = guess_urls("https://acme.com/tr/")
    assert "https://acme.com/iletisim" in urls
    assert "https://acme.com/tr/iletisim" in urls


def test_parse_sites():
    text = "acme.com\n\n# comment\nhttps://www.acme.com/\nHTTP://Shop.io/tr\nnot a url\nacme.com/team"
    assert parse_sites(text) == ["https://acme.com", "HTTP://Shop.io/tr", "https://acme.com/team"]


def test_scrape_sites_runs_in_parallel_and_reports_each_site():
    pages = {f"https://site{i}.com": f"info@site{i}.com" for i in range(12)}
    seen = []
    summary = scrape_sites(
        list(pages), lambda index: FakeFetcher(pages), options=ScrapeOptions(workers=4),
        progress=lambda result, total: seen.append((result.site, total)),
    )
    assert len(summary.results) == 12 and summary.count(FOUND) == 12
    assert {site for site, _ in seen} == set(pages) and all(total == 12 for _, total in seen)


def test_scrape_sites_can_be_stopped():
    stop = threading.Event()
    pages = {f"https://site{i}.com": "x" for i in range(50)}

    def progress(result, total):
        stop.set()

    summary = scrape_sites(list(pages), lambda i: FakeFetcher(pages),
                           options=ScrapeOptions(workers=2), progress=progress, cancelled=stop.is_set)
    assert summary.stopped
    assert len(summary.results) < 50
