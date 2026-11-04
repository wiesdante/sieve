import pytest

from sieve.core.email_scraper import (
    BLOCKED,
    FAILED,
    FORM_ONLY,
    FOUND,
    PARKED,
    FetchResult,
    ScrapeOptions,
    scan_site,
)
from sieve.core.site_discovery import (
    detect_languages,
    fold,
    guess_urls,
    is_blocked,
    is_parked,
    parse_sitemap,
    same_site,
    score_link,
    site_key,
    sitemaps_from_robots,
    toggle_www,
)

pytest.importorskip("bs4")
ALL = ("en", "tr", "de")


class Site:
    def __init__(self, pages, statuses=None):
        self.pages = pages
        self.statuses = statuses or {}
        self.requested = []

    def fetch(self, url, quick=False):
        self.requested.append(url)
        if url in self.pages:
            return FetchResult(url, text=self.pages[url], status=self.statuses.get(url, 200))
        return FetchResult(url, text="<html>Not found</html>", status=404)


# ------------------------------------------------------------------- scoring
def test_fold_handles_turkish_and_german():
    assert fold("/Bize-Ulaşın") == "bize ulasin"
    assert fold("Über uns") == "uber uns"
    assert fold("Datenschutzerklärung") == "datenschutzerklarung"


@pytest.mark.parametrize(
    ("href", "text", "minimum"),
    [
        ("/impressum", "Impressum", 110),
        ("/kontakt", "Kontakt", 100),
        ("/iletisim", "İletişim", 100),
        ("/bize-ulasin", "Bize Ulaşın", 100),
        ("/contact-us", "Contact us", 100),
        ("/kvkk", "KVKK Aydınlatma Metni", 50),
        ("/kunye", "Künye", 60),
        ("/datenschutz", "Datenschutz", 50),
        ("/ueber-uns", "Über uns", 30),
    ],
)
def test_contact_and_legal_pages_score_high(href, text, minimum):
    assert score_link(href, text, ALL) >= minimum


@pytest.mark.parametrize(
    ("href", "text"),
    [
        ("/products/contact-lens", "Contact lenses"),
        ("/urunler/iletisim-kablosu", "İletişim kablosu"),
        ("/blog/how-to-contact-customers", "How to contact customers"),
        ("/downloads/kontakt.pdf", "Kontakt (PDF)"),
        ("/shop", "Shop"),
    ],
)
def test_misleading_links_score_low(href, text):
    assert score_link(href, text, ALL) < 30


def test_impressum_outranks_about():
    assert score_link("/impressum", "Impressum", ALL) > score_link("/ueber-uns", "Über uns", ALL)


# ------------------------------------------------------------------ language
@pytest.mark.parametrize(
    ("lang", "url", "text", "first"),
    [
        ("de-DE", "https://firma.com", "", "de"),
        (None, "https://firma.com.tr", "", "tr"),
        (None, "https://firma.at", "", "de"),
        (None, "https://firma.com", "Ürünlerimiz ve hizmetlerimiz için bizimle iletişime geçin", "tr"),
        (None, "https://firma.com", "Wir sind für Sie da und freuen uns über Ihre Nachricht", "de"),
        (None, "https://firma.com", "Welcome to our shop", "en"),
    ],
)
def test_detect_languages(lang, url, text, first):
    languages = detect_languages(lang, url, text)
    assert languages[0] == first and "en" in languages


def test_guess_urls_follow_language_order():
    urls = guess_urls("https://firma.de/", ("de", "en"))
    assert urls[0] == "https://firma.de/impressum"
    assert urls.index("https://firma.de/kontakt") < urls.index("https://firma.de/contact")


# ------------------------------------------------------------- site identity
def test_site_key_and_same_site():
    assert site_key("https://shop.acme.com.tr/x") == "acme.com.tr"
    assert site_key("www.firma.de") == "firma.de"
    assert site_key("https://a.b.co.uk") == "b.co.uk"
    assert same_site("https://shop.acme.com", "https://www.acme.com/contact")
    assert not same_site("https://acme.com", "https://other.com")


def test_toggle_www():
    assert toggle_www("https://acme.com/x") == "https://www.acme.com/x"
    assert toggle_www("https://www.acme.com") == "https://acme.com"


# ------------------------------------------------------------------ sitemaps
def test_sitemaps():
    assert sitemaps_from_robots("User-agent: *\nSitemap: https://a.com/s.xml\nsitemap: https://a.com/b.xml") == [
        "https://a.com/s.xml", "https://a.com/b.xml"]
    pages, children = parse_sitemap("<urlset><url><loc>https://a.com/x?a=1&amp;b=2</loc></url></urlset>")
    assert pages == ["https://a.com/x?a=1&b=2"] and children == []
    pages, children = parse_sitemap("<sitemapindex><sitemap><loc>https://a.com/p.xml</loc></sitemap></sitemapindex>")
    assert pages == [] and children == ["https://a.com/p.xml"]


# ------------------------------------------------------------ page verdicts
def test_parked_detection():
    assert is_parked("https://sedo.com/search/details?domain=x", "")
    assert is_parked("https://x.com", "This domain is for sale! Make an offer.")
    assert is_parked("https://x.com.tr", "Bu alan adı satılıktır.")
    assert is_parked("https://x.de", "Diese Domain steht zum Verkauf.")
    assert not is_parked("https://news.com", "Article: why this domain is for sale ... " + "x" * 5000)


def test_blocked_detection():
    assert is_blocked(503, "<html><head><title>Just a moment...</title></head>")
    assert is_blocked(403, '<div id="cf-chl-widget"></div>')
    assert is_blocked(429, "")
    # A normal page with a reCAPTCHA contact form is not "blocked".
    assert not is_blocked(200, '<form><div class="g-recaptcha"></div><textarea></textarea></form>')


# ------------------------------------------------------------- scan scenarios
def test_german_site_goes_straight_to_impressum():
    site = Site({
        "https://firma.de": '<html lang="de"><a href="/ueber-uns">Über uns</a>'
                            '<a href="/impressum">Impressum</a><a href="/produkte">Produkte</a></html>',
        "https://firma.de/impressum": "Verantwortlich: Max Muster, E-Mail: buero@firma.de",
        "https://firma.de/ueber-uns": "Team: chef@firma.de",
    })
    result = scan_site("https://firma.de", site)
    assert result.status == FOUND
    assert [found.email for found in result.emails] == ["buero@firma.de"]
    assert "https://firma.de/ueber-uns" not in site.requested
    assert result.language == "de"


def test_structured_data_is_read_and_trusted_first():
    page = """<html><script type="application/ld+json">
      {"@type": "Organization", "contactPoint": {"email": "mailto:info@acme.com"}}
    </script><span itemprop="email">sales@acme.com</span></html>"""
    result = scan_site("https://acme.com", Site({"https://acme.com": page}))
    assert [(found.email, found.how) for found in result.emails] == [
        ("info@acme.com", "structured"), ("sales@acme.com", "structured")]


def test_sitemap_finds_contact_page_without_links():
    site = Site({
        "https://shop.com.tr": "<html>Hoş geldiniz</html>",
        "https://shop.com.tr/robots.txt": "Sitemap: https://shop.com.tr/sitemap.xml",
        "https://shop.com.tr/sitemap.xml": "<urlset><loc>https://shop.com.tr/urun/1</loc>"
                                           "<loc>https://shop.com.tr/sayfa/iletisim-bilgileri</loc></urlset>",
        "https://shop.com.tr/sayfa/iletisim-bilgileri": "E-posta: destek@shop.com.tr",
    })
    result = scan_site("https://shop.com.tr", site)
    assert [found.email for found in result.emails] == ["destek@shop.com.tr"]
    assert not any(url[-9:] == "/iletisim" for url in site.requested)  # no guessing needed


def test_contact_form_only():
    site = Site({
        "https://acme.com": '<a href="/contact">Contact</a>',
        "https://acme.com/contact": "<form><input name='email'><textarea name='message'></textarea></form>",
    })
    result = scan_site("https://acme.com", site)
    assert result.status == FORM_ONLY
    assert result.contact_form == "https://acme.com/contact"


def test_parked_and_blocked_sites_stop_immediately():
    parked = Site({"https://old.com": "<html><body>This domain is for sale!</body></html>"})
    assert scan_site("https://old.com", parked).status == PARKED
    assert parked.requested == ["https://old.com"]

    blocked = Site({"https://safe.com": "<title>Just a moment...</title>"}, {"https://safe.com": 503})
    assert scan_site("https://safe.com", blocked).status == BLOCKED

    denied = Site({"https://deny.com": "Forbidden"}, {"https://deny.com": 403})
    result = scan_site("https://deny.com", denied)
    assert result.status == BLOCKED and "403" in result.error

    broken = Site({"https://broken.com": "Server error"}, {"https://broken.com": 500})
    assert scan_site("https://broken.com", broken).status == FAILED


def test_page_budget_is_respected():
    links = "".join(f'<a href="/about-{i}">About {i}</a>' for i in range(30))
    site = Site({"https://big.com": links})
    result = scan_site("https://big.com", site, options=ScrapeOptions(page_budget=5))
    assert result.pages <= 5 and len(site.requested) <= 5


def test_subdomain_links_are_followed():
    site = Site({
        "https://www.acme.com": '<a href="https://destek.acme.com/iletisim">İletişim</a>',
        "https://destek.acme.com/iletisim": "destek@acme.com",
    })
    assert scan_site("https://www.acme.com", site).emails[0].email == "destek@acme.com"
