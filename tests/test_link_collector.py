import threading
import time

import pytest

pytest.importorskip("bs4")

from sieve.core.email_scraper import (  # noqa: E402
    BROWSER_ALWAYS,
    BROWSER_OFF,
    BROWSER_SMART,
    FetchResult,
)
from sieve.core.link_collector import (  # noqa: E402
    BLOCKED,
    EXTERNAL,
    FAILED,
    INTERNAL,
    NO_LINKS,
    READ,
    CollectOptions,
    HostThrottle,
    LinkFilterSettings,
    clean_url,
    collect_links,
    is_social,
    link_key,
    parse_links,
    parse_pages,
    parse_rules,
)


class Site:
    def __init__(self, pages, statuses=None, name="Fake browser"):
        self.pages = pages
        self.statuses = statuses or {}
        self.requested = []
        self.name = name

    def fetch(self, url, quick=False):
        self.requested.append(url)
        if url in self.pages:
            return FetchResult(url, text=self.pages[url], status=self.statuses.get(url, 200))
        return FetchResult(url, text="<html>Not found</html>", status=404)


DIRECTORY = """
<html><body>
<nav><a href="/">Home</a><a href="/about">About</a></nav>
<ul>
  <li><a href="https://acme.com/?utm_source=expo">ACME Ltd</a></li>
  <li><a href="https://www.firma.com.tr/tr/anasayfa#top">Firma A.Ş.</a></li>
  <li><a href="https://shop.acme.com/catalog.pdf">Catalogue</a></li>
  <li><a href="//beta.io/">Beta</a></li>
</ul>
<a href="https://www.facebook.com/expo">Facebook</a>
<a href="https://twitter.com/intent/tweet?url=x">Share</a>
<a href="mailto:info@expo.com">Mail</a><a href="javascript:void(0)">JS</a><a href="#list">Top</a>
<a href="https://www.google.com/maps/place/Expo">Map</a>
</body></html>
"""


def run(pages, site, **options):
    filters = options.pop("filters", LinkFilterSettings())
    return collect_links(pages, lambda _i: site, CollectOptions(filters=filters, host_interval=0, **options))


# ---------------------------------------------------------------- tidying
def test_clean_url_drops_fragment_and_tracking():
    assert clean_url("https://ACME.com/a?utm_source=x&id=5&fbclid=1#top") == "https://acme.com/a?id=5"
    assert clean_url("https://acme.com/a?utm_source=x", strip_tracking=False) == "https://acme.com/a?utm_source=x"
    assert clean_url("https://acme.com") == "https://acme.com/"


def test_link_key_ignores_scheme_www_and_trailing_slash():
    assert link_key("http://www.acme.com/about/") == link_key("https://acme.com/about")


def test_social_and_maps_links():
    assert is_social("https://www.facebook.com/expo")
    assert is_social("https://m.youtube.com/watch?v=1")
    assert is_social("https://www.google.com.tr/maps/place/x")
    assert not is_social("https://www.google.com/search?q=x")
    assert not is_social("https://facebookmarketing.example.com/")


def test_parse_pages_adds_scheme_and_removes_duplicates():
    assert parse_pages("expo.com/list\nhttps://expo.com/list/\n# note\n\nftp://x.com") == ["https://expo.com/list"]


def test_parse_rules():
    assert parse_rules("  /login \n# comment\nWIKIPEDIA\n/login") == ["/login", "wikipedia"]


def test_parse_links_resolves_and_skips_non_web_links():
    parsed = parse_links(DIRECTORY, "https://expo.com/exhibitors")
    urls = [url for url, _ in parsed.links]
    assert "https://beta.io/" in urls
    assert "https://expo.com/about" in urls
    assert not any(url.startswith(("mailto:", "javascript:")) for url in urls)
    assert ("https://acme.com/?utm_source=expo", "ACME Ltd") in parsed.links


# ---------------------------------------------------------------- filters
def test_default_filters_keep_company_links_and_drop_noise():
    site = Site({"https://expo.com/exhibitors": DIRECTORY})
    result = run(["https://expo.com/exhibitors"], site).results[0]
    kept = [link.url for link in result.links]
    assert "https://acme.com/" in kept  # tracking removed
    assert "https://www.firma.com.tr/tr/anasayfa" in kept  # fragment removed
    assert not any("facebook" in url or "twitter" in url or "google.com/maps" in url for url in kept)
    assert not any(url.endswith(".pdf") for url in kept)
    reasons = dict(result.rejected)
    assert reasons["https://www.facebook.com/expo"] == "Social, share or app link"
    assert reasons["https://shop.acme.com/catalog.pdf"] == "File download"
    assert result.status == READ


def test_other_sites_only():
    site = Site({"https://expo.com/exhibitors": DIRECTORY})
    filters = LinkFilterSettings(scope=EXTERNAL)
    kept = [link.url for link in run(["https://expo.com/exhibitors"], site, filters=filters).results[0].links]
    assert "https://expo.com/about" not in kept and "https://acme.com/" in kept


def test_same_site_only():
    site = Site({"https://expo.com/exhibitors": DIRECTORY})
    filters = LinkFilterSettings(scope=INTERNAL)
    kept = [link.url for link in run(["https://expo.com/exhibitors"], site, filters=filters).results[0].links]
    assert set(kept) == {"https://expo.com/", "https://expo.com/about"}


def test_home_pages_only_gives_one_link_per_site():
    site = Site({"https://expo.com/exhibitors": DIRECTORY})
    filters = LinkFilterSettings(scope=EXTERNAL, home_pages_only=True)
    kept = [link.url for link in run(["https://expo.com/exhibitors"], site, filters=filters).results[0].links]
    # shop.acme.com and acme.com are the same site
    assert kept == ["https://acme.com/", "https://www.firma.com.tr/", "https://beta.io/"]


def test_exclude_rules():
    site = Site({"https://expo.com/exhibitors": DIRECTORY})
    filters = LinkFilterSettings(exclude=["firma", "/about"])
    result = run(["https://expo.com/exhibitors"], site, filters=filters).results[0]
    kept = [link.url for link in result.links]
    assert not any("firma" in url or "/about" in url for url in kept)
    assert dict(result.rejected)["https://expo.com/about"] == "Exclude rule: /about"


def test_page_without_links_that_pass():
    site = Site({"https://expo.com/": '<a href="https://facebook.com/x">fb</a>'})
    result = run(["https://expo.com/"], site).results[0]
    assert result.status == NO_LINKS and result.error == "No links passed the filters"


# ------------------------------------------------------------- browser use
def test_smart_mode_uses_browser_for_blocked_page():
    plain = Site({"https://expo.com/": "<title>Just a moment...</title>"}, {"https://expo.com/": 503})
    browser = Site({"https://expo.com/": '<a href="https://acme.com/">ACME</a>'})
    result = collect_links(
        ["https://expo.com/"], lambda _i: plain,
        CollectOptions(browser=BROWSER_SMART, host_interval=0, host_penalty=0),
        browser_for=lambda _i: browser,
    ).results[0]
    assert result.status == READ and result.via == "both"
    assert [link.url for link in result.links] == ["https://acme.com/"]


def test_smart_mode_uses_browser_when_page_shows_no_links():
    plain = Site({"https://app.com/": '<div id="root"></div>'})
    browser = Site({"https://app.com/": '<a href="https://acme.com/">ACME</a>'})
    result = collect_links(
        ["https://app.com/"], lambda _i: plain, CollectOptions(host_interval=0),
        browser_for=lambda _i: browser,
    ).results[0]
    assert [link.url for link in result.links] == ["https://acme.com/"]


def test_always_mode_skips_plain_requests():
    plain = Site({})
    browser = Site({"https://expo.com/": '<a href="https://acme.com/">ACME</a>'})
    result = collect_links(
        ["https://expo.com/"], lambda _i: plain, CollectOptions(browser=BROWSER_ALWAYS, host_interval=0),
        browser_for=lambda _i: browser,
    ).results[0]
    assert plain.requested == [] and result.via == "browser"


def test_blocked_page_is_retried_once_after_a_pause():
    class Flaky(Site):
        def fetch(self, url, quick=False):
            self.requested.append(url)
            if len(self.requested) == 1:
                return FetchResult(url, text="<p>Too many requests</p>", status=429)
            return FetchResult(url, text='<a href="https://acme.com/">ACME</a>', status=200)

    flaky = Flaky({})
    result = collect_links(
        ["https://expo.com/"], lambda _i: flaky,
        CollectOptions(browser=BROWSER_OFF, host_interval=0, host_penalty=0.2),
    ).results[0]
    assert result.status == READ and len(flaky.requested) == 2


def test_missing_page_and_dead_domain():
    class Dead:
        def fetch(self, url, quick=False):
            return FetchResult(url, error="Domain not found")

    summary = collect_links(["https://gone.example/", "https://expo.com/x"],
                            lambda i: Dead() if i == 0 else Site({}), CollectOptions(host_interval=0))
    statuses = {result.url: (result.status, result.error) for result in summary.results}
    assert statuses["https://gone.example/"] == (FAILED, "Domain not found")
    assert statuses["https://expo.com/x"] == (FAILED, "The page answered HTTP 404")


def test_access_denied_counts_as_blocked():
    site = Site({"https://expo.com/": "<p>Forbidden</p>"}, {"https://expo.com/": 403})
    result = run(["https://expo.com/"], site, browser=BROWSER_OFF, host_penalty=0).results[0]
    assert result.status == BLOCKED


# --------------------------------------------------------------- throttle
def test_throttle_spaces_requests_to_the_same_host():
    throttle = HostThrottle(interval=0.2, penalty=0.5)
    started = time.monotonic()
    for _ in range(3):
        throttle.wait("expo.com")
    assert time.monotonic() - started >= 0.38
    other = time.monotonic()
    throttle.wait("other.com")
    assert time.monotonic() - other < 0.1


def test_throttle_wait_ends_when_stopped():
    throttle = HostThrottle(interval=0, penalty=30)
    throttle.penalize("expo.com")
    stop = threading.Event()
    threading.Timer(0.2, stop.set).start()
    started = time.monotonic()
    throttle.wait("expo.com", stop.is_set)
    assert time.monotonic() - started < 2


def test_thin_page_with_scripts_is_opened_in_the_browser():
    plain = Site({"https://quotes.com/js/": '<a href="/">Home</a><a href="/login">Login</a>'
                                            '<script>var data = [];</script>'})
    browser = Site({"https://quotes.com/js/": '<a href="/">Home</a><a href="/author/a">A</a>'
                                              '<a href="/author/b">B</a><a href="/author/c">C</a>'})
    result = collect_links(
        ["https://quotes.com/js/"], lambda _i: plain, CollectOptions(host_interval=0),
        browser_for=lambda _i: browser,
    ).results[0]
    assert len(result.links) == 4 and result.via == "both"
