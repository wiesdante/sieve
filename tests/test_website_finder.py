import threading
import time

import pytest

pytest.importorskip("bs4")

from sieve.core import website_finder as wf  # noqa: E402
from sieve.core.website_finder import (  # noqa: E402
    FAILED,
    FOUND,
    MATCH_DOMAIN,
    NO_SITE,
    RATE_LIMITED,
    UNSURE,
    Connections,
    FinderSettings,
    SearchPage,
    SearchResult,
    company_name,
    domain_match,
    find_website,
    find_websites,
    is_home_page,
    judge_results,
    not_a_company_site,
    parse_block_rules,
    parse_companies,
    parse_search_page,
)

SETTINGS = FinderSettings()


def results(*items):
    return [SearchResult(url, title) for url, title in items]


# ------------------------------------------------------------- name parsing
def test_legal_forms_are_ignored():
    name = company_name("ACME Savunma Sanayi ve Ticaret A.Ş.")
    assert name.tokens == ("acme", "savunma")
    assert name.distinctive == ("acme",)
    assert company_name("Hobbywing Technology Co., Ltd.").tokens == ("hobbywing", "technology")
    assert company_name("Koç Holding").distinctive == ("koc",)


# ----------------------------------------------------------- domain matching
@pytest.mark.parametrize(
    ("company", "url"),
    [
        ("Elbit Systems", "https://elbitsystems.com/"),
        ("Bird Aerosystems", "https://www.birdaero.com/"),
        ("MKE", "https://www.mke.gov.tr/"),
        ("Makina ve Kimya Endüstrisi", "https://www.mke.gov.tr/"),
        ("Israel Aerospace Industries", "https://www.iai.co.il/"),
        ("Rafael Advanced Defense Systems", "https://www.rafael.co.il/"),
        ("Koç Holding", "https://www.koc.com.tr/"),
        ("ASELSAN A.Ş.", "https://www.aselsan.com/tr"),
        ("Hobbywing Technology Co., Ltd.", "https://www.hobbywing.com/en/"),
        ("Regula Forensics", "https://regulaforensics.com/"),
        ("Altimus Tech", "https://www.altimus-tech.lt/"),
        ("Excalibur Army", "https://www.excaliburarmy.cz/"),
        ("Delta Defence", "https://deltadefence.sk/en/"),
        ("Bagira Systems", "https://www.bagirasys.com/"),
        ("Fırat Plastik Kauçuk", "https://www.firat.com/"),
        ("Ünlü Tekstil", "https://www.unlutekstil.com.tr/"),
    ],
)
def test_domains_that_belong_to_the_company(company, url):
    assert domain_match(url, company_name(company)) == MATCH_DOMAIN


@pytest.mark.parametrize(
    ("company", "url"),
    [
        ("Acme Savunma", "https://www.acmetools.com/"),
        ("Delta Defence", "https://www.defence.gov.sk/"),
        ("Global Defence Systems", "https://www.globalsecurity.org/"),
        ("Bird Aerosystems", "https://www.aerosystems.com/"),
        ("Koç Holding", "https://www.kochind.com/"),
        ("Rafael Advanced Defense Systems", "https://www.advanceddefense.com/"),
    ],
)
def test_domains_that_do_not_belong_to_the_company(company, url):
    assert domain_match(url, company_name(company)) != MATCH_DOMAIN


# ------------------------------------------------------- non-company sites
@pytest.mark.parametrize(
    ("url", "reason"),
    [
        ("https://www.linkedin.com/company/acme", "Social media and video"),
        ("https://tr.linkedin.com/company/acme", "Social media and video"),
        ("https://www.instagram.com/acme/", "Social media and video"),
        ("https://www.amazon.com.tr/s?k=acme", "Marketplaces and shops"),
        ("https://www.trendyol.com/acme", "Marketplaces and shops"),
        ("https://acme.shopier.com/", "Marketplaces and shops"),
        ("https://www.kompass.com/c/acme/tr123/", "Business directories and company data"),
        ("https://www.europages.co.uk/ACME/00000004.html", "Business directories and company data"),
        ("https://en.wikipedia.org/wiki/Acme", "Encyclopedias, news and finance"),
        ("https://acme.wixsite.com/acme", "Website-builder and hosting profiles"),
        ("https://acme.business.site/", "Website-builder and hosting profiles"),
        ("https://sites.google.com/view/acme", "Website-builder and hosting profiles"),
        ("https://www.kariyer.net/firma/acme", "Job sites and company reviews"),
        ("https://www.tripadvisor.com.tr/Hotel-acme", "Maps, reviews and travel"),
        ("https://acme.com/catalogue.pdf", "A file, not a website"),
    ],
)
def test_sites_that_are_not_a_company_website(url, reason):
    assert not_a_company_site(url, SETTINGS) == reason


def test_platform_names_inside_other_domains_are_not_blocked():
    # The script's substring check would have blocked these.
    for url in ("https://www.betsy.com/", "https://www.amazonia-logistics.com/", "https://www.next.com.tr/"):
        assert not_a_company_site(url, SETTINGS) is None


def test_the_platform_itself_is_allowed_when_it_is_the_company():
    assert not_a_company_site("https://www.trendyol.com/", SETTINGS, company_name("Trendyol").label) is None


def test_switched_off_category_and_own_block_list():
    settings = FinderSettings(categories=frozenset({"social"}), block=parse_block_rules(
        "https://www.firmabul.com/\n/firma/  # profile pages\n"))
    assert not_a_company_site("https://en.wikipedia.org/wiki/Acme", settings) is None
    assert not_a_company_site("https://tr.firmabul.com/acme", settings) == "Your block list: firmabul.com"
    assert not_a_company_site("https://other.com/firma/acme", settings) == "Your block list: /firma/"


def test_home_page_shapes():
    for url in ("https://a.com", "https://a.com/", "https://a.com/en/", "https://a.com/tr-tr/anasayfa",
                "https://a.com/index.php", "https://a.com/?lang=en"):
        assert is_home_page(url), url
    for url in ("https://a.com/company/acme", "https://a.com/?id=179", "https://a.com/a/b/c"):
        assert not is_home_page(url), url


# --------------------------------------------------------------- choosing
def test_first_own_site_is_chosen_and_home_page_reported():
    outcome = judge_results("Bird Aerosystems", results(
        ("https://www.linkedin.com/company/bird-aerosystems", "Bird Aerosystems | LinkedIn"),
        ("https://www.kompass.com/c/bird/il1/", "BIRD AEROSYSTEMS - Kompass"),
        ("https://www.birdaero.com/products/amips/", "AMIPS - Bird Aerosystems"),
    ), SETTINGS)
    assert outcome.status == FOUND
    assert outcome.website == "https://www.birdaero.com/"
    assert outcome.found_url == "https://www.birdaero.com/products/amips/"
    assert outcome.rank == 3 and outcome.match == "Domain matches the name"
    assert [c.verdict for c in outcome.candidates] == ["skipped", "skipped", "found"]


def test_unrelated_home_page_on_top_is_not_taken():
    outcome = judge_results("Acme Savunma", results(
        ("https://www.acmetools.com/", "Acme Tools"),
        ("https://www.someblog.com/2024/acme-savunma-news", "Some news"),
    ), SETTINGS)
    assert outcome.status == UNSURE  # close, but never mixed into the websites
    assert outcome.website == "https://www.acmetools.com/"


def test_nothing_matching_means_no_website():
    outcome = judge_results("Acme Savunma", results(
        ("https://www.linkedin.com/company/acme-savunma", "Acme Savunma | LinkedIn"),
        ("https://www.randomnews.com/article", "Unrelated"),
    ), SETTINGS)
    assert outcome.status == NO_SITE and outcome.website == ""


def test_page_title_finds_an_abbreviated_domain():
    outcome = judge_results("Türk Havacılık ve Uzay Sanayii", results(
        ("https://www.tusas.com/", "TUSAŞ | Türk Havacılık ve Uzay Sanayii A.Ş."),
    ), SETTINGS)
    assert outcome.status == FOUND and outcome.match == "Page title names the company"


def test_title_match_on_a_deep_page_or_profile_is_only_unsure():
    deep = judge_results("Türk Havacılık ve Uzay Sanayii", results(
        ("https://www.firmalar.com/firma/12345", "Türk Havacılık ve Uzay Sanayii - Firma bilgileri"),
    ), SETTINGS)
    assert deep.status == UNSURE
    profile = judge_results("Türk Havacılık ve Uzay Sanayii", results(
        ("https://tusas.someplatform.com/", "Türk Havacılık ve Uzay Sanayii"),
    ), SETTINGS)
    assert profile.status == UNSURE


def test_domain_match_beats_an_earlier_title_match():
    outcome = judge_results("Czechoslovak Group", results(
        ("https://www.czechpress.cz/", "Czechoslovak Group"),
        ("https://www.czechoslovakgroup.cz/en", "CSG"),
    ), SETTINGS)
    assert outcome.website == "https://www.czechoslovakgroup.cz/"


# ------------------------------------------------------------ result pages
HTML_PAGE = """
<html><body><form id="search_form" action="/html/"><input name="q"></form>
<div id="links" class="results">
 <div class="result results_links results_links_deep result--ad">
   <a class="result__a" href="https://duckduckgo.com/y.js?ad_domain=ads.com&u3=x">Buy Acme</a></div>
 <div class="result results_links results_links_deep web-result">
   <h2><a class="result__a" href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fwww.birdaero.com%2F&amp;rut=abc">
   Bird Aerosystems</a></h2><a class="result__snippet">Airborne protection</a></div>
 <div class="result results_links results_links_deep web-result">
   <h2><a class="result__a" href="https://www.linkedin.com/company/bird">Bird | LinkedIn</a></h2></div>
</div></body></html>
"""

LITE_PAGE = """
<html><body><form action="/lite/"><input name="q"></form><table>
<tr class="result-sponsored"><td><a class="result-link" href="https://duckduckgo.com/y.js?x=1">Ad</a></td></tr>
<tr><td><a rel="nofollow" href="https://www.aselsan.com/" class="result-link">ASELSAN</a></td></tr>
<tr><td class="result-snippet">Defence electronics</td></tr>
</table></body></html>
"""


def test_reads_results_and_skips_ads():
    page = parse_search_page(200, HTML_PAGE)
    assert page.kind == "results"
    assert [r.url for r in page.results] == ["https://www.birdaero.com/", "https://www.linkedin.com/company/bird"]
    assert page.results[0].title == "Bird Aerosystems"


def test_reads_the_lite_page():
    page = parse_search_page(200, LITE_PAGE)
    assert [r.url for r in page.results] == ["https://www.aselsan.com/"]
    assert page.results[0].snippet == "Defence electronics"


@pytest.mark.parametrize(
    ("status", "html"),
    [
        (202, "<html></html>"),
        (200, '<div class="anomaly-modal__title">Unfortunately, bots use DuckDuckGo too.</div>'),
        (200, '<form id="challenge-form"></form>'),
        (429, ""),
    ],
)
def test_bot_checks_and_rate_limits_are_recognised(status, html):
    assert parse_search_page(status, html).kind == "limited"


def test_only_duckduckgos_own_note_means_no_results():
    assert parse_search_page(200, '<div class="no-results">No results.</div>').kind == "no_results"
    # An empty or changed page is not "no website".
    assert parse_search_page(200, "<html><body><div id='links'></div></body></html>").kind == "unexpected"
    assert parse_search_page(200, "").kind == "unexpected"


# ---------------------------------------------------- searching end to end
class FakeSearcher:
    def __init__(self, pages):
        self.pages = list(pages)
        self.calls = []

    def search(self, query, region="", lite=False):
        self.calls.append((query, lite))
        page = self.pages.pop(0) if self.pages else SearchPage("no_results")
        if isinstance(page, str):
            return SearchPage("unexpected"), page
        return page, None


def connections(searchers, cooldown=0.0, penalty=0.0):
    conns = Connections(list(range(len(searchers))) if len(searchers) > 1 else None,
                        lambda entry: searchers[entry or 0])
    conns._cooldown = cooldown
    conns._penalty = penalty
    return conns


def test_rate_limit_is_retried_and_never_reported_as_no_website():
    searcher = FakeSearcher([SearchPage("limited", detail="DuckDuckGo asked to slow down (HTTP 202)"),
                             SearchPage("results", results(("https://www.aselsan.com/", "ASELSAN")))])
    result = find_website("Aselsan", connections([searcher]), SETTINGS)
    assert result.status == FOUND and result.searches == 2
    assert searcher.calls[1][1] is True  # second try uses the lite page


def test_rate_limited_every_time_is_reported_as_such():
    limited = SearchPage("limited", detail="DuckDuckGo asked to slow down (HTTP 202)")
    result = find_website("Aselsan", connections([FakeSearcher([limited] * 9)]), SETTINGS)
    assert result.status == RATE_LIMITED and result.website == ""


def test_unexpected_pages_end_as_failed_not_no_website():
    result = find_website("Aselsan", connections([FakeSearcher([SearchPage("unexpected", detail="x")] * 9)]),
                          SETTINGS)
    assert result.status == FAILED


def test_broken_proxy_is_dropped_and_others_keep_working():
    broken = FakeSearcher(["Proxy error"] * 20)
    working = FakeSearcher([SearchPage("results", results(("https://www.aselsan.com/", "A")))] * 20)
    conns = connections([broken, working])
    names = ["Aselsan"] * 1
    for _ in range(6):
        find_website(names[0], conns, SETTINGS)
    assert conns.alive() == 1


def test_all_proxies_dead_fails_quickly():
    conns = connections([FakeSearcher(["Proxy error"] * 20), FakeSearcher(["Proxy error"] * 20)])
    started = time.monotonic()
    for _ in range(4):
        result = find_website("Aselsan", conns, SETTINGS)
    assert result.status == FAILED and "proxy" in result.error.lower()
    assert time.monotonic() - started < 3


def test_connections_rest_between_searches():
    searcher = FakeSearcher([])
    conns = connections([searcher], cooldown=0.3)
    started = time.monotonic()
    for _ in range(3):
        slot = conns.acquire()
        conns.release(slot, "ok")
    assert time.monotonic() - started >= 0.5


def test_waiting_for_a_connection_ends_when_stopped():
    conns = connections([FakeSearcher([])], cooldown=30)
    conns.release(conns.acquire(), "ok")
    stop = threading.Event()
    threading.Timer(0.2, stop.set).start()
    started = time.monotonic()
    assert conns.acquire(stop.is_set) is None
    assert time.monotonic() - started < 2


def test_whole_run_keeps_each_company_with_its_site():
    pages = {
        "Aselsan": SearchPage("results", results(("https://www.aselsan.com/tr", "ASELSAN"))),
        "Nobody Ltd": SearchPage("no_results"),
    }

    class ByName:
        def search(self, query, region="", lite=False):
            return pages[query], None

    conns = Connections(None, lambda _e: ByName())
    conns._cooldown = 0
    summary = find_websites(["Aselsan", "Nobody Ltd"], conns, SETTINGS, workers=2)
    by_company = {r.company: (r.status, r.website) for r in summary.results}
    assert by_company == {"Aselsan": (FOUND, "https://www.aselsan.com/"), "Nobody Ltd": (NO_SITE, "")}


def test_parse_companies_removes_repeats():
    assert parse_companies("Aselsan\n  aselsan \n\nRoketsan  A.Ş.\n") == ["Aselsan", "Roketsan A.Ş."]


def test_direct_connection_rests_longer_than_proxies():
    assert wf.DIRECT_COOLDOWN < wf.PROXY_COOLDOWN or wf.DIRECT_COOLDOWN > 0


def test_run_gives_up_quickly_when_every_connection_keeps_being_limited():
    limited = SearchPage("limited", detail="DuckDuckGo asked to slow down (HTTP 202)")

    class AlwaysLimited:
        def search(self, query, region="", lite=False):
            return limited, None

    conns = Connections(None, lambda _e: AlwaysLimited())
    conns._cooldown = 0
    conns._penalty = 0.01
    started = time.monotonic()
    summary = find_websites([f"Company {n}" for n in range(20)], conns, SETTINGS, workers=1)
    assert time.monotonic() - started < 5
    assert {r.status for r in summary.results} == {RATE_LIMITED}
    assert "retry later or turn on proxies" in summary.results[-1].error


def test_a_success_resets_the_limit_count():
    conns = connections([FakeSearcher([])], penalty=0.0)
    for _ in range(2):
        conns.release(conns.acquire(), "limited")
    conns.release(conns.acquire(), "ok")
    conns.release(conns.acquire(), "limited")
    assert not conns.exhausted


def test_a_media_company_keeps_its_own_news_site():
    outcome = judge_results("ARMY RECOGNITION GROUP", results(
        ("https://www.armyrecognition.com/", "Army Recognition"),
    ), SETTINGS)
    assert outcome.status == FOUND and outcome.website == "https://www.armyrecognition.com/"


def test_browser_searcher_reads_the_page_and_reports_errors():
    from sieve.core.email_scraper import FetchResult
    from sieve.core.website_finder import BrowserSearcher

    class Fetcher:
        def __init__(self, result):
            self.result = result
            self.urls = []

        def fetch(self, url, quick=False):
            self.urls.append(url)
            return self.result

    ok = Fetcher(FetchResult("x", text=HTML_PAGE, status=200))
    page, error = BrowserSearcher(ok).search("Bird Aerosystems", "tr-tr")
    assert error is None and page.kind == "results"
    assert ok.urls == ["https://html.duckduckgo.com/html/?q=Bird+Aerosystems&kl=tr-tr"]
    page, error = BrowserSearcher(Fetcher(FetchResult("x", error="Browser timed out"))).search("A", lite=True)
    assert page.kind == "unexpected" and error == "Browser timed out"


def test_missing_browser_fails_at_once_with_a_clear_message():
    class NoBrowser:
        def search(self, query, region="", lite=False):
            return SearchPage("unexpected"), "Browser not available: no supported browser could be started"

    result = find_website("Aselsan", connections([NoBrowser()]), SETTINGS)
    assert result.status == FAILED and "Chrome or Microsoft Edge" in result.error
    assert result.searches == 1


def test_status_tells_what_the_run_waits_for():
    conns = connections([FakeSearcher([])], penalty=0.6)
    conns.release(conns.acquire(), "limited")
    waiter = threading.Thread(target=conns.acquire)
    waiter.start()
    time.sleep(0.2)
    assert "slow down" in conns.status.text
    waiter.join(3)
