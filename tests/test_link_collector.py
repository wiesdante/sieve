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


# -------------------------------------------------------------- pagination
def paged_site():
    pages = {}
    for number in range(1, 5):
        nxt = f'<a class="next page-numbers" href="/list?page={number + 1}">Sonraki</a>' if number < 4 else ""
        pages[f"https://expo.com/list?page={number}"] = (
            f'<a href="https://company{number}.com/">Company {number}</a>{nxt}'
        )
    pages["https://expo.com/list"] = pages.pop("https://expo.com/list?page=1")
    pages["https://expo.com/list"] = pages["https://expo.com/list"].replace("?page=2", "?page=2")
    return Site(pages)


def test_follows_next_pages_up_to_the_limit():
    site = paged_site()
    result = run(["https://expo.com/list"], site, max_pages=3).results[0]
    assert [link.url for link in result.links] == [
        "https://company1.com/", "https://company2.com/", "https://company3.com/"
    ]
    assert result.pages == 3


def test_without_following_only_the_page_itself_is_read():
    site = paged_site()
    result = run(["https://expo.com/list"], site).results[0]
    assert len(result.links) == 1 and site.requested == ["https://expo.com/list"]


@pytest.mark.parametrize(
    "html",
    [
        '<link rel="next" href="/p2">',
        '<a href="/p2" rel="next">2</a>',
        '<a href="/p2">Next ›</a>',
        '<a href="/p2">Weiter</a>',
        '<a href="/p2" aria-label="Next page"><svg></svg></a>',
        '<a href="/p2">»</a>',
        '<a href="/p2">Следующая</a>',
        '<a href="/p2">다음</a>',
        '<li class="next"><a href="/p2">Next <span aria-hidden="true">→</span></a></li>',
        '<a href="/p2">› Sonraki</a>',
    ],
)
def test_next_page_detection(html):
    assert parse_links(html, "https://expo.com/p1").next_page == "https://expo.com/p2"


def test_next_page_must_be_on_the_same_site():
    assert parse_links('<a href="https://other.com/p2">Next</a>', "https://expo.com/p1").next_page is None


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


def test_browser_is_kept_for_the_following_pages():
    plain = Site({"https://expo.com/list": "<title>Just a moment...</title>"}, {"https://expo.com/list": 403})
    browser = Site({
        "https://expo.com/list": '<a href="https://a.com/">A</a><a href="/list?p=2">Next</a>',
        "https://expo.com/list?p=2": '<a href="https://b.com/">B</a>',
    })
    result = collect_links(
        ["https://expo.com/list"], lambda _i: plain,
        CollectOptions(max_pages=5, host_interval=0, host_penalty=0),
        browser_for=lambda _i: browser,
    ).results[0]
    assert [link.url for link in result.links] == ["https://a.com/", "https://b.com/"]
    assert plain.requested == ["https://expo.com/list"]


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


# ------------------------------------------------- pagination completeness
from sieve.core.link_collector import PARTIAL, expand_range  # noqa: E402


def numbered_site(count, with_next=True, pager_class="pagination", break_at=None, cap=None):
    """A list of ``count`` pages at /list?page=N, one company per page."""
    pages = {}
    shown = cap or count
    for number in range(1, count + 1):
        links = "".join(
            f'<a href="/list?page={n}"{" aria-current=page" if n == number else ""}>{n}</a>'
            for n in range(1, shown + 1)
        )
        nxt = f'<a href="/list?page={number + 1}">Next</a>' if with_next and number < count else ""
        pages[f"https://dir.com/list?page={number}"] = (
            f'<a href="https://company{number}.com/">Company {number}</a>'
            f'<div class="{pager_class}">{links}{nxt}</div>'
        )
    if break_at:
        del pages[f"https://dir.com/list?page={break_at}"]
    return Site(pages)


def run_list(site, max_pages=50):
    return collect_links(["https://dir.com/list?page=1"], lambda _i: site,
                         CollectOptions(max_pages=max_pages, host_interval=0, host_penalty=0,
                                        browser=BROWSER_OFF)).results[0]


def test_reads_every_page_and_reports_the_last_one():
    result = run_list(numbered_site(5))
    assert [link.url for link in result.links] == [f"https://company{n}.com/" for n in range(1, 6)]
    assert result.status == READ and result.pages_read == 5 and result.expected_pages == 5
    assert result.note == "Last page reached (5 of 5 pages read)"


def test_follows_page_numbers_when_there_is_no_next_link():
    result = run_list(numbered_site(4, with_next=False))
    assert result.pages_read == 4 and result.status == READ
    assert any("Next page (page number)" in line for line in result.log)


def test_a_page_that_fails_midway_marks_the_entry_partial():
    result = run_list(numbered_site(5, break_at=3))
    assert result.status == PARTIAL and result.pages_read == 2
    assert "page 3 could not be read" in result.note


def test_reaching_the_limit_with_more_pages_left_is_partial():
    result = run_list(numbered_site(8), max_pages=3)
    assert result.status == PARTIAL and result.pages_read == 3
    assert result.note == "Stopped at the limit of 3 pages; there are more pages (the list has 8)"


def test_single_page_mode_mentions_that_more_pages_exist():
    result = run_list(numbered_site(8), max_pages=1)
    assert result.status == READ
    assert "more pages" in result.note


def test_gap_between_page_numbers_and_missing_next_is_reported():
    class Gap(Site):
        pass

    site = numbered_site(6)
    # page 3 shows no next link and no link to page 4, but says there are 6 pages
    site.pages["https://dir.com/list?page=3"] = (
        '<a href="https://company3.com/">C3</a><p>Page 3 of 6</p>'
        '<div class="pagination"><a href="/list?page=1">1</a><a href="/list?page=2">2</a></div>'
    )
    result = run_list(site)
    assert result.status == PARTIAL and result.pages_read == 3
    assert "goes up to page 6" in result.note and "page 4" in result.note


def test_site_repeating_its_last_page_is_treated_as_the_end():
    site = numbered_site(3)
    # page 3 has a next link, but page 4 shows the same list as page 3
    site.pages["https://dir.com/list?page=3"] += '<a href="/list?page=4">Next</a>'
    site.pages["https://dir.com/list?page=4"] = site.pages["https://dir.com/list?page=3"]
    result = run_list(site)
    assert result.pages_read == 4 and result.status == READ
    assert "repeated" in result.note
    assert len(result.links) == 3


def test_load_more_button_is_reported():
    site = Site({"https://dir.com/list?page=1": '<a href="https://a.com/">A</a><button>Load more</button>'})
    result = run_list(site)
    assert result.status == PARTIAL and "button" in result.note


def test_page_x_of_y_text_sets_the_expected_count():
    html = '<a href="https://a.com/">A</a><span>Sayfa 2 / 9</span><a href="/l?p=3">Sonraki</a>'
    info = parse_links(html, "https://dir.com/l?p=2").pagination
    assert info.highest == 9 and info.current == 2 and info.next_url == "https://dir.com/l?p=3"


def test_results_count_text_sets_the_expected_count():
    html = '<p>Showing 21–40 of 95 results</p><a href="https://a.com/">A</a>'
    assert parse_links(html, "https://dir.com/l").pagination.highest == 5


def test_numbers_outside_a_pager_are_not_page_numbers():
    html = ('<div class="page-content"><a href="/note/1">1</a><a href="/note/2">2</a>'
            '<a href="/year/2024">2024</a></div><p>10-12/2024</p>')
    info = parse_links(html, "https://dir.com/article").pagination
    assert info.highest is None and info.next_url is None


def test_page_range_expands_in_order():
    assert expand_range("https://dir.com/list?page={1-3}") == [
        "https://dir.com/list?page=1", "https://dir.com/list?page=2", "https://dir.com/list?page=3"
    ]
    assert parse_pages("dir.com/p/{2..4}/") == [
        "https://dir.com/p/2/", "https://dir.com/p/3/", "https://dir.com/p/4/"
    ]


@pytest.mark.parametrize(
    ("link", "current", "expected"),
    [
        ("https://news.com/news?p=2", "https://news.com/news", True),
        ("https://blog.com/page/3/", "https://blog.com/page/2/", True),
        ("https://blog.com/page/2/", "https://blog.com/", True),
        ("https://dir.com/list?cat=5&page=4", "https://dir.com/list?cat=5&page=3", True),
        ("https://dir.com/list?cat=6&page=4", "https://dir.com/list?cat=5&page=3", False),
        ("https://dir.com/list?page=5", "https://dir.com/list?page=3", False),
    ],
)
def test_next_address(link, current, expected):
    from sieve.core.link_collector import is_next_address

    assert is_next_address(link, current) is expected


def test_more_link_is_followed_by_its_address():
    html = '<a href="https://a.com/">A</a><a href="news?p=2" class="morelink">More</a>'
    info = parse_links(html, "https://news.com/news").pagination
    assert info.next_url == "https://news.com/news?p=2" and info.next_how == "next address"
