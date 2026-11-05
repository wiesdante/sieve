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
from sieve.core.site_discovery import LANGUAGES as ALL  # noqa: E402


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


# ------------------------------------------------- cases from a real 20-site test
def test_rot13_hidden_addresses_are_decoded():
    page = """<html><body>
      <a class="enc" data-address="nvnq@nvnq.vg">Email</a>
      <span data-x="nvnq@crp.vg"></span><span data-x="oehkryyrf@nvnq.vg"></span>
    </body></html>"""
    result = scan_site("https://aiad.it", Site({"https://aiad.it": page}))
    assert {found.email for found in result.emails} == {"aiad@aiad.it", "aiad@pec.it", "bruxelles@aiad.it"}
    assert all(found.how == "decoded" for found in result.emails)


def test_reversed_addresses_are_decoded():
    page = '<p>Mail: <span style="direction: rtl; unicode-bidi: bidi-override">moc.emca@ofni</span></p>'
    result = scan_site("https://acme.com", Site({"https://acme.com": page}))
    assert [found.email for found in result.emails] == ["info@acme.com"]


def test_library_author_in_page_code_is_rejected():
    page = """<html><script>/*! GSAP 3.12 https://gsap.com | jack@greensock.com */ var x=1;</script>
      <p>Contact: space_technology@4ig.hu</p></html>"""
    result = scan_site("https://4igsdt.hu", Site({"https://4igsdt.hu": page}))
    assert [found.email for found in result.emails] == ["space_technology@4ig.hu"]
    assert ("jack@greensock.com", "Only in page code, other domain") in result.rejected


def test_own_domain_address_in_page_code_is_kept():
    page = '<html><script>var contact = "sales@acme.com";</script></html>'
    result = scan_site("https://acme.com", Site({"https://acme.com": page}))
    assert [(f.email, f.how) for f in result.emails] == [("sales@acme.com", "source")]


def test_www_in_email_domain_is_removed():
    result = scan_site("https://www.bagirasys.com", Site({"https://www.bagirasys.com": "info@www.bagirasys.com"}))
    assert [found.email for found in result.emails] == ["info@bagirasys.com"]


@pytest.mark.parametrize("status", [401, 451])
def test_access_denied_statuses_are_blocked(status):
    site = Site({"https://rbc.ru": "Unauthorized"}, {"https://rbc.ru": status})
    result = scan_site("https://rbc.ru", site)
    assert result.status == BLOCKED and str(status) in result.error


def test_slow_server_is_not_retried_with_variants():
    class Slow(Site):
        def fetch(self, url, quick=False):
            self.requested.append(url)
            return FetchResult(url, error="Read timed out")

    slow = Slow({})
    result = scan_site("https://bsvt.by/en/", slow)
    assert result.status == FAILED
    assert slow.requested == ["https://bsvt.by/en/"]


# ------------------------------------------------------------ many languages
@pytest.mark.parametrize(
    ("href", "text"),
    [
        ("/contatti", "Contatti"),
        ("/contacto", "Contáctenos"),
        ("/nous-contacter", "Nous contacter"),
        ("/kontakty", "Kontakty"),
        ("/kapcsolat", "Kapcsolat"),
        ("/kontaktai", "Kontaktai"),
        ("/contacts", "Контакты"),
        ("/kontakti", "Контакти"),
        ("/sub/contact", "연락처"),
        ("/inquiry", "お問い合わせ"),
        ("/about/contact", "联系我们"),
        ("/contact", "צור קשר"),
        ("/contact", "اتصل بنا"),
        ("/epikoinonia", "Επικοινωνία"),
        ("/lien-he", "Liên hệ"),
    ],
)
def test_contact_pages_in_many_languages(href, text):
    assert score_link(href, text, ALL) >= 100


def test_russian_requisites_and_japanese_company_profile_are_useful():
    assert score_link("/rekvizity", "Реквизиты", ALL) >= 60
    assert score_link("/company", "会社概要", ALL) >= 60


@pytest.mark.parametrize(
    ("lang", "url", "first"),
    [
        ("ko-KR", "https://www.bontech.kr", "ko"),
        (None, "https://www.bontech.kr", "ko"),
        ("it", "https://aiad.it", "it"),
        (None, "https://bsvt.by/en/", "ru"),
        ("uk", "https://firm.com.ua", "ru"),
        ("hu-HU", "https://4igsdt.hu", "hu"),
        ("sv-SE", "https://firma.se", "nordic"),
    ],
)
def test_detect_more_languages(lang, url, first):
    assert detect_languages(lang, url)[0] == first


def test_korean_site_finds_contact_page():
    site = Site({
        "https://www.bontech.kr": '<html lang="ko"><a href="/sub/sub05_01.php">회사소개</a>'
                                  '<a href="/sub/sub05_03.php">오시는 길</a><a href="/sub/sub04_01.php">제품</a></html>',
        "https://www.bontech.kr/sub/sub05_03.php": "주소 ... 이메일: sales@bontech.kr",
    })
    result = scan_site("https://www.bontech.kr", site)
    assert [found.email for found in result.emails] == ["sales@bontech.kr"]


def test_international_guess_paths():
    urls = guess_urls("https://firma.it/", ("it", "en"))
    assert urls[0] == "https://firma.it/contatti"
    assert "https://firma.it/en/contact" in urls


# ------------------------------------------------------------- browser mode
from sieve.core.email_scraper import (  # noqa: E402
    BROWSER_ALWAYS,
    BROWSER_OFF,
    BROWSER_SMART,
    EMPTY,
    looks_js_rendered,
)


def test_smart_mode_retries_blocked_site_in_browser():
    plain = Site({"https://guarded.com": "<title>Just a moment...</title>"}, {"https://guarded.com": 503})
    browser = Site({"https://guarded.com": "<p>Write to info@guarded.com</p>"})
    result = scan_site("https://guarded.com", plain, options=ScrapeOptions(browser=BROWSER_SMART), browser=browser)
    assert result.status == FOUND and result.via == "browser"
    assert [found.email for found in result.emails] == ["info@guarded.com"]
    assert result.pages == 2
    assert any("Retrying in the browser" in line for line in result.log)


def test_smart_mode_does_not_open_browser_when_plain_scan_found_addresses():
    plain = Site({"https://ok.com": "info@ok.com"})
    browser = Site({})
    result = scan_site("https://ok.com", plain, options=ScrapeOptions(browser=BROWSER_SMART), browser=browser)
    assert result.via == "http" and browser.requested == []


def test_smart_mode_renders_javascript_sites():
    shell = '<html><body><div id="root"></div><script src="/app.js"></script></body></html>'
    plain = Site({"https://spa.com": shell})
    browser = Site({"https://spa.com": '<div id="root"><a href="/contact">Contact</a></div>',
                    "https://spa.com/contact": "Email: hello@spa.com"})
    result = scan_site("https://spa.com", plain, options=ScrapeOptions(browser=BROWSER_SMART), browser=browser)
    assert [found.email for found in result.emails] == ["hello@spa.com"]
    assert result.via == "browser"


def test_always_mode_uses_browser_for_pages_and_plain_requests_for_sitemaps():
    plain = Site({"https://a.com/robots.txt": "", "https://a.com": "should not be used"})
    browser = Site({"https://a.com": "Welcome", "https://a.com/contact": "info@a.com"})
    result = scan_site("https://a.com", plain, options=ScrapeOptions(browser=BROWSER_ALWAYS), browser=browser)
    assert result.via == "browser" and result.emails[0].email == "info@a.com"
    assert "https://a.com/robots.txt" in plain.requested
    assert "https://a.com" not in plain.requested


def test_missing_browser_keeps_plain_result_with_a_note():
    class NoBrowser:
        def fetch(self, url, quick=False):
            return FetchResult(url, error="Browser not available: Microsoft Edge could not be started")

    plain = Site({"https://e.com": "Nothing here"})
    result = scan_site("https://e.com", plain, options=ScrapeOptions(browser=BROWSER_SMART), browser=NoBrowser())
    assert result.status == EMPTY and result.via == "http"
    assert any("Browser not available" in line for line in result.log)


def test_browser_off_never_uses_browser():
    plain = Site({"https://e.com": "Nothing here"})
    browser = Site({"https://e.com": "info@e.com"})
    result = scan_site("https://e.com", plain, options=ScrapeOptions(browser=BROWSER_OFF), browser=browser)
    assert result.status == EMPTY and browser.requested == []


def test_js_rendered_detection():
    assert looks_js_rendered('<div id="__next"></div>', "")
    assert looks_js_rendered("<html>", "You need to enable JavaScript to run this app.")
    assert not looks_js_rendered("<p>" + "word " * 200 + "</p>", "word " * 200)
