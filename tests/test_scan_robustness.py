"""Cases from a real 67-site run: stuck sites, Stop, parking redirects and odd answers."""

import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

pytest.importorskip("bs4")

from sieve.core import email_scraper  # noqa: E402
from sieve.core.email_filter import EmailFilter, prepare_text  # noqa: E402
from sieve.core.email_scraper import (  # noqa: E402
    BLOCKED,
    FAILED,
    FOUND,
    PARKED,
    FetchResult,
    HttpFetcher,
    ScrapeOptions,
    scan_site,
    scrape_sites,
)
from sieve.core.link_extractor import find_emails  # noqa: E402
from sieve.core.site_discovery import guess_urls, page_key, score_link  # noqa: E402


class Site:
    """Fake fetcher: url -> html, or url -> (final_url, html, status)."""

    def __init__(self, pages):
        self.pages = pages
        self.requested = []

    def fetch(self, url, quick=False):
        self.requested.append(url)
        page = self.pages.get(url)
        if page is None:
            return FetchResult(url, text="<html>Not found</html>", status=404)
        if isinstance(page, tuple):
            final, text, status = page
            return FetchResult(final, text=text, status=status)
        return FetchResult(url, text=page, status=200)


# ------------------------------------------------------------ address cleanup
def test_escaped_newline_is_not_glued_to_the_address():
    source = 'var footer = "Mail us:\\ninfo@excalibur.cz\\tor call";'
    assert find_emails(prepare_text(source)) == ["info@excalibur.cz"]


def test_template_placeholder_domains_are_junk():
    junk = EmailFilter()
    assert not junk.judge("info@website.com").ok
    assert junk.judge("sage@gosage.com").ok


# ---------------------------------------------------------------- discovery
def test_guesses_drop_query_strings():
    urls = guess_urls("https://www.bontech.kr/?ckattempt=1", ("en",))
    assert all("ckattempt" not in url for url in urls)


def test_page_key_ignores_scheme_www_fragment_and_language_folder():
    assert page_key("https://www.a.com/contact/") == page_key("http://a.com/contact#form")
    assert page_key("https://a.com/es/contact-us/", ignore_language=True) == page_key(
        "https://a.com/contact-us", ignore_language=True
    )
    assert page_key("https://a.com/es/contact-us") != page_key("https://a.com/contact-us")


def test_news_article_with_contact_word_scores_low():
    article = "/bird-aerosystems-receives-order-to-protect-additional-two-helicopters-un-contacts/"
    assert score_link(article, "", ("en",)) < score_link("/contact-us/", "", ("en",)) - 50


def test_same_contact_page_in_other_languages_is_not_reopened():
    site = Site({
        "https://bird.com": '<a href="/contact-us/">Contact</a><a href="/es/contact-us/">Contacto</a>'
                            '<a href="/ru/contact-us/">Контакты</a>',
        "https://bird.com/contact-us/": "<p>Call us</p>",
        "https://bird.com/es/contact-us/": "<p>Llámenos</p>",
    })
    scan_site("https://bird.com", site)
    assert "https://bird.com/contact-us/" in site.requested
    assert "https://bird.com/es/contact-us/" not in site.requested
    assert "https://bird.com/ru/contact-us/" not in site.requested


def test_same_page_with_fragment_is_not_reopened():
    site = Site({
        "https://rynex.com": '<a href="/contact/">Contact</a><a href="/contact/#form">Write</a>',
        "https://rynex.com/contact/": "<p>No address here</p>",
    })
    scan_site("https://rynex.com", site)
    assert sum(url.startswith("https://rynex.com/contact/") for url in site.requested) == 1


# ------------------------------------------------------------------ statuses
def test_redirect_to_parking_service_is_parked():
    site = Site({"https://ushgroup.net": (
        "http://findonlineresults.com/?dn=ushgroup.net&pid=9PO7", "<p>Related searches</p>", 200
    )})
    result = scan_site("https://ushgroup.net", site)
    assert result.status == PARKED


def test_unusual_status_code_counts_as_blocked():
    site = Site({"https://www.iai.co.il": ("https://www.iai.co.il/", "<p>Hello</p>", 247)})
    result = scan_site("https://www.iai.co.il", site)
    assert result.status == BLOCKED and "247" in result.error


def test_missing_page_falls_back_to_the_home_page():
    site = Site({
        "https://www.roe.ru/en/": ("https://www.roe.ru/en/", "<p>Not found</p>", 404),
        "https://www.roe.ru/": "<p>Write to roe@roe.ru</p>",
    })
    result = scan_site("https://www.roe.ru/en/", site)
    assert result.status == FOUND
    assert result.emails[0].email == "roe@roe.ru"


def test_unanswered_host_is_not_retried_over_http():
    class Dead:
        requested = []

        def fetch(self, url, quick=False):
            self.requested.append(url)
            return FetchResult(url, error="Connection timed out")

    dead = Dead()
    scan_site("https://dss.sc.gov", dead)
    assert dead.requested == ["https://dss.sc.gov", "https://www.dss.sc.gov"]


# ---------------------------------------------------------- stuck sites, Stop
class Frozen:
    """A fetcher that never returns until released (a site that hangs forever)."""

    def __init__(self):
        self.release = threading.Event()

    def fetch(self, url, quick=False):
        self.release.wait(30)
        return FetchResult(url, error="released")


def test_a_stuck_site_is_given_up_and_the_run_finishes(monkeypatch):
    monkeypatch.setattr(email_scraper, "SITE_HARD_LIMIT", 0.5)
    frozen = Frozen()
    fast = Site({"https://ok.com": "<p>info@ok.com</p>"})
    options = ScrapeOptions(workers=2, site_time_limit=0.1)
    started = time.monotonic()
    summary = scrape_sites(
        ["https://stuck.com", "https://ok.com"],
        lambda index: frozen if index == 0 else fast,
        options=options,
    )
    frozen.release.set()
    assert time.monotonic() - started < 5
    statuses = {result.site: result.status for result in summary.results}
    assert statuses == {"https://ok.com": FOUND, "https://stuck.com": FAILED}
    assert "Gave up" in next(r.error for r in summary.results if r.site == "https://stuck.com")


def test_stop_returns_even_when_a_site_is_stuck(monkeypatch):
    monkeypatch.setattr(email_scraper, "STOP_GRACE", 0.3)
    frozen = Frozen()
    stop = threading.Event()
    threading.Timer(0.3, stop.set).start()
    started = time.monotonic()
    summary = scrape_sites(["https://stuck.com"], lambda index: frozen, cancelled=stop.is_set)
    frozen.release.set()
    assert time.monotonic() - started < 3
    assert summary.stopped


# --------------------------------------------------------- Retry-After header
class SlowDown(BaseHTTPRequestHandler):
    def do_GET(self):  # noqa: N802
        body = b"<p>Maintenance</p>"
        self.send_response(503)
        self.send_header("Retry-After", "3600")
        self.send_header("Content-Type", "text/html")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


def test_retry_after_header_does_not_stall_the_fetch():
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), SlowDown)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    try:
        started = time.monotonic()
        result = HttpFetcher().fetch(f"http://127.0.0.1:{httpd.server_address[1]}/")
        assert time.monotonic() - started < 5
        assert result.status == 503
    finally:
        httpd.shutdown()


# ------------------------------------------------------------ second 67-site run
from sieve.core.email_scraper import BROWSER_SMART  # noqa: E402


def test_parking_seen_only_in_the_browser_wins_over_no_emails():
    plain = Site({"https://ushgroup.net": "<p>Welcome</p>"})
    browser = Site({"https://ushgroup.net": (
        "http://findonlineresults.com/?dn=ushgroup.net", "<p>Related searches</p>", 200
    )})
    result = scan_site("https://ushgroup.net", plain, options=ScrapeOptions(browser=BROWSER_SMART),
                       browser=browser)
    assert result.status == PARKED and result.via == "browser"


def test_timed_out_site_gets_one_browser_try_without_variants():
    class Dead:
        def fetch(self, url, quick=False):
            return FetchResult(url, error="Connection timed out")

    browser = Site({"https://www.rafael.co.il": "<p>Write to info@rafael.co.il</p>"})
    result = scan_site("https://www.rafael.co.il", Dead(), options=ScrapeOptions(browser=BROWSER_SMART),
                       browser=browser)
    assert result.status == FOUND
    assert browser.requested[0] == "https://www.rafael.co.il"
    assert not any(url.startswith("http://") for url in browser.requested)


def test_refused_connection_is_not_retried_in_the_browser():
    class Refused:
        def fetch(self, url, quick=False):
            return FetchResult(url, error="Connection refused")

    browser = Site({})
    scan_site("https://down.com", Refused(), options=ScrapeOptions(browser=BROWSER_SMART), browser=browser)
    assert browser.requested == []


def test_redirect_to_an_already_read_page_is_not_read_again():
    class Redirecting(Site):
        def fetch(self, url, quick=False):
            if url == "https://gosage.com/contact?ref=footer":
                self.requested.append(url)
                return FetchResult("https://gosage.com/contact/", text="<p>again</p>", status=200)
            return super().fetch(url, quick)

    site = Redirecting({
        "https://gosage.com": '<a href="/contact/">Contact</a><a href="/contact?ref=footer">Contact us</a>',
        "https://gosage.com/contact/": "<p>No address</p>",
    })
    result = scan_site("https://gosage.com", site)
    assert sum("Visited https://gosage.com/contact/" in line for line in result.log) == 1


def test_scan_stops_after_two_contact_pages_add_nothing():
    site = Site({
        "https://yugo.com": '<p>office@yugo.com</p><a href="/en/contact">Contact</a>'
                            '<a href="/kontakt">Kontakt</a><a href="/lat/kontakt">Kontakt</a>'
                            '<a href="/sr/kontakt-nas">Kontakt nas</a>',
        "https://yugo.com/en/contact": "<p>Call us</p>",
        "https://yugo.com/kontakt": "<p>Pozovite</p>",
        "https://yugo.com/lat/kontakt": "<p>Pozovite</p>",
        "https://yugo.com/sr/kontakt-nas": "<p>Pozovite</p>",
    })
    result = scan_site("https://yugo.com", site)
    assert result.status == FOUND
    assert result.pages == 3


def test_browser_fetcher_carries_cookies_between_pages():
    from sieve.core.browser import BrowserFetcher

    class Pool:
        name = "Fake"
        available = True

        def __init__(self):
            self.seen_states = []

        def fetch_with_state(self, url, quick, proxy, state):
            self.seen_states.append(state)
            return FetchResult(url, text="", status=200), {"cookies": [{"name": "ck", "value": "1"}]}

    pool = Pool()
    fetcher = BrowserFetcher(pool)
    fetcher.fetch("https://bontech.kr/")
    fetcher.fetch("https://bontech.kr/contact")
    assert pool.seen_states == [None, {"cookies": [{"name": "ck", "value": "1"}]}]
