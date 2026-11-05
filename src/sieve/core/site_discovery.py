"""Understanding a website well enough to find where its contact details are.

Pure functions, no network: language detection, ranking links that lead to
contact/legal pages in many languages, reading schema.org data, parsing
sitemaps and recognising parked domains, bot-protection pages and contact forms.
"""

from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import dataclass
from urllib.parse import unquote, urljoin, urlsplit

# --------------------------------------------------------------- page scoring
# (pattern, score) per language. Patterns are matched against folded text: lower
# case, accents removed, separators turned into spaces. A page that legally or by
# convention carries an email address scores highest. English, Turkish and German
# are covered most thoroughly; the others cover the usual contact/legal/about pages.
_RULES: dict[str, list[tuple[str, int]]] = {
    "en": [
        (r"contacts?(?: us)?|get in touch|reach us|write to us|contact information", 100),
        (r"imprint|legal notice|legal information|site notice", 70),
        (r"privacy(?: policy| notice)?|data protection|gdpr", 40),
        (r"about(?: us)?|our company|who we are|company|team", 30),
        (r"support|help ?desk|customer service", 25),
    ],
    "tr": [
        (r"iletisim(?: bilgileri)?|bize ulasin|irtibat|ulasim ve iletisim", 100),
        (r"kunye", 60),
        (r"kvkk|kisisel verilerin korunmasi|aydinlatma metni|gizlilik(?: politikasi)?", 50),
        (r"musteri hizmetleri", 40),
        (r"hakkimizda|kurumsal|biz kimiz|ekibimiz", 30),
        (r"destek|yardim", 20),
    ],
    "de": [
        (r"impressum", 110),
        (r"kontakt(?:formular)?|kontaktieren|so erreichen sie uns|ansprechpartner", 100),
        (r"datenschutz(?:erklarung)?|datenschutzhinweise", 50),
        (r"uber uns|ueber uns|unternehmen|wir uber uns|team", 30),
        (r"kundenservice|hilfe|support", 25),
    ],
    "fr": [
        (r"contactez nous|nous contacter|contact", 100),
        (r"mentions legales", 70),
        (r"politique de confidentialite", 40),
        (r"a propos|qui sommes nous|notre societe", 30),
    ],
    "it": [
        (r"contatti|contattaci|contattateci|contatto", 100),
        (r"note legali", 60),
        (r"chi siamo|azienda", 30),
    ],
    "es": [
        (r"contacto|contactenos|contactanos|contactar", 100),
        (r"aviso legal", 70),
        (r"politica de privacidad", 40),
        (r"quienes somos|sobre nosotros|empresa", 30),
    ],
    "pt": [
        (r"contato|contacto|contactos|fale conosco|fale connosco", 100),
        (r"quem somos|sobre nos|empresa", 30),
    ],
    "nl": [
        (r"neem contact op|contact", 100),
        (r"colofon", 60),
        (r"over ons", 30),
    ],
    "pl": [(r"kontakty?", 100), (r"o nas|o firmie", 30), (r"polityka prywatnosci", 40)],
    "cs": [(r"kontakty?", 100), (r"o nas|o spolecnosti|o firme", 30)],
    "hu": [
        (r"kapcsolat|elerhetosegek?|kapcsolatfelvetel", 100),
        (r"impresszum", 70),
        (r"adatvedelem", 40),
        (r"rolunk|cegunkrol", 30),
    ],
    "ro": [(r"contact|contacteaza ne", 100), (r"despre noi", 30)],
    "sh": [(r"kontakti?|kontaktirajte nas", 100), (r"o nama|o nas", 30)],
    "lt": [(r"kontaktai", 100), (r"apie mus|apie imone", 30)],
    "lv": [(r"kontakti", 100), (r"par mums|par uznemumu", 30)],
    "et": [(r"kontakt", 100), (r"meist|ettevottest", 30)],
    "nordic": [
        (r"kontakt(?:a oss| os| oss)?|ota yhteytta|yhteystiedot", 100),
        (r"om oss|om os|om foretaget|meista|yritys", 30),
    ],
    "ru": [
        (r"контакты|контакт|контакти|связаться с нами|свяжитесь с нами|обратная связь|"
         r"зв.язатися|звязок", 100),
        (r"реквизиты", 60),
        (r"о компании|о нас|за нас|за компанията|про нас|про компанію", 30),
    ],
    "el": [(r"επικοινωνια", 100), (r"σχετικα με εμας|εταιρεια", 30)],
    "he": [(r"צור קשר|יצירת קשר", 100), (r"אודות", 30)],
    "ar": [(r"اتصل بنا|تواصل معنا|اتصال", 100), (r"من نحن", 30)],
    "vi": [(r"lien he", 100), (r"gioi thieu|ve chung toi", 30)],
    "id": [(r"hubungi kami|kontak", 100), (r"tentang kami", 30)],
}
# Scripts without spaces between words: matched without word boundaries.
_UNBOUNDED_RULES: dict[str, list[tuple[str, int]]] = {
    "ko": [(r"연락처|문의|고객센터|오시는 ?길|찾아오시는 ?길", 100), (r"회사소개|회사 소개", 30)],
    "ja": [(r"お問い合わせ|お問合せ|問い合わせ|問合せ|連絡先", 100), (r"会社概要", 60), (r"会社案内|企業情報", 30)],
    "zh": [(r"联系我们|聯繫我們|聯絡我們|联系方式|聯絡方式", 100), (r"关于我们|關於我們|公司简介|公司簡介", 30)],
}

LANGUAGES = tuple(_RULES) + tuple(_UNBOUNDED_RULES)

_NEGATIVE = re.compile(
    r"\b(products?|shop|store|cart|basket|checkout|category|categories|catalog(?:ue)?|blog|news|"
    r"article|login|log in|register|sign up|account|careers?|jobs?|"
    r"urun(?:ler)?|sepet|kategori|haber(?:ler)?|giris|uye ol|kariyer|"
    r"produkte?|warenkorb|kategorie|aktuelles|anmelden|registrieren|karriere|stellen|"
    r"produits|prodotti|productos|produtos|produkty|termekek|actualites|notizie|noticias|novinky|"
    r"продукция|товары|каталог|новости)\b"
)
_FILE_LINK = re.compile(r"\.(?:pdf|jpe?g|png|gif|webp|svg|zip|rar|docx?|xlsx?|pptx?|mp4|mp3)(?:$|[?#])", re.I)

_FOLD = str.maketrans({
    "ı": "i", "İ": "i", "ß": "ss", "ł": "l", "Ł": "l", "ø": "o", "Ø": "o", "đ": "d", "Đ": "d",
    "æ": "ae", "Æ": "ae", "œ": "oe", "ŀ": "l", "’": " ", "'": " ",
})


def strip_accents(text: str) -> str:
    """Remove accents and diacritics (é→e, ş→s, ü→u, ą→a, й→и) and lower-case."""
    text = text.translate(_FOLD)
    decomposed = unicodedata.normalize("NFKD", text)
    return "".join(ch for ch in decomposed if not unicodedata.combining(ch)).lower()


def fold(text: str) -> str:
    """Lower-case, remove accents, turn separators into spaces."""
    text = strip_accents(unquote(text))
    return re.sub(r"[\s/_\-.+%]+", " ", text).strip()


def _compile(rules: dict[str, list[tuple[str, int]]], bounded: bool) -> dict:
    compiled = {}
    for language, items in rules.items():
        compiled[language] = []
        for pattern, score in items:
            pattern = strip_accents(pattern)
            regex = rf"(?<!\w)(?:{pattern})(?!\w)" if bounded else pattern
            compiled[language].append((re.compile(regex), score))
    return compiled


_COMPILED = {**_compile(_RULES, True), **_compile(_UNBOUNDED_RULES, False)}


_ARTICLE_SLUG_WORDS = 5


def score_link(href: str, text: str, languages: tuple[str, ...]) -> int:
    """How likely the link leads to a page with contact details (0 = not at all)."""
    if _FILE_LINK.search(href):
        return 0
    path = urlsplit(href).path
    folded_path, folded_text = fold(path), fold(text)
    slug = path.rstrip("/").rsplit("/", 1)[-1]
    best = 0
    for language in languages:
        for pattern, score in _COMPILED.get(language, ()):
            in_text = bool(pattern.search(folded_text))
            in_path = bool(pattern.search(folded_path))
            if in_text or in_path:
                best = max(best, score + (10 if in_text and in_path else 0))
    if best and (_NEGATIVE.search(folded_path) or _NEGATIVE.search(folded_text)):
        best -= 90
    if best and len(re.split(r"[-_]+", slug)) >= _ARTICLE_SLUG_WORDS:
        best -= 60  # "company-receives-order-...-contacts" is a news article, not a contact page
    return max(best, 0)


# ------------------------------------------------------------------ language
_TLD_LANGUAGE = {
    "tr": "tr", "de": "de", "at": "de", "ch": "de", "li": "de", "fr": "fr", "be": "fr",
    "it": "it", "es": "es", "mx": "es", "ar": "es", "cl": "es", "co": "es", "pe": "es",
    "pt": "pt", "br": "pt", "nl": "nl", "pl": "pl", "cz": "cs", "sk": "cs", "hu": "hu",
    "ro": "ro", "md": "ro", "hr": "sh", "rs": "sh", "si": "sh", "ba": "sh", "me": "sh",
    "lt": "lt", "lv": "lv", "ee": "et", "se": "nordic", "no": "nordic", "dk": "nordic",
    "fi": "nordic", "ru": "ru", "by": "ru", "ua": "ru", "bg": "ru", "kz": "ru",
    "gr": "el", "cy": "el", "il": "he", "sa": "ar", "ae": "ar", "eg": "ar", "qa": "ar",
    "kw": "ar", "jo": "ar", "vn": "vi", "id": "id", "my": "id", "kr": "ko", "jp": "ja",
    "cn": "zh", "tw": "zh", "hk": "zh",
}
# Declared page languages that share a rule set.
_LANGUAGE_ALIASES = {
    "sk": "cs", "hr": "sh", "sr": "sh", "sl": "sh", "bs": "sh", "uk": "ru", "bg": "ru",
    "be": "ru", "kk": "ru", "sv": "nordic", "no": "nordic", "nb": "nordic", "nn": "nordic",
    "da": "nordic", "fi": "nordic", "ms": "id", "iw": "he",
}

# Letters are matched case-sensitively: with IGNORECASE, "ı" would also match "I".
_TR_HINT = re.compile(r"[şğıŞĞİ]|\b(?:ve|ile|için|hakkımızda|iletişim|ürünler)\b")
_DE_HINT = re.compile(r"[äßÄ]|\b(?:und|der|die|das|für|über uns|Impressum|Kontakt)\b")


def _language_code(code: str) -> str | None:
    code = (code or "").strip().lower().replace("_", "-").split("-")[0]
    code = _LANGUAGE_ALIASES.get(code, code)
    return code if code in LANGUAGES else None


def detect_languages(html_lang: str | None, url: str, text: str = "") -> tuple[str, ...]:
    """Languages of the site, most likely first; English is always included.

    Uses the page's declared language, then the country ending of the domain,
    then a quick look at the text.
    """
    found: list[str] = []
    declared = _language_code(html_lang or "")
    if declared:
        found.append(declared)
    host = urlsplit(url).hostname or ""
    by_tld = _TLD_LANGUAGE.get(host.rsplit(".", 1)[-1])
    if by_tld and by_tld not in found:
        found.append(by_tld)
    if not found and text:
        sample = text[:20000]
        tr, de = len(_TR_HINT.findall(sample)), len(_DE_HINT.findall(sample))
        if max(tr, de) >= 3 or (max(tr, de) >= 1 and len(sample) < 2000):
            found.append("tr" if tr >= de else "de")
    if "en" not in found:
        found.append("en")
    return tuple(found)


_INTERNATIONAL = ("/en/contact", "/en/contacts", "/en/contact-us", "/contacts")
_GUESS_PATHS = {
    "en": ("/contact", "/contact-us", "/contacts", "/about", "/about-us", "/imprint", "/legal",
           "/privacy-policy"),
    "tr": ("/iletisim", "/bize-ulasin", "/hakkimizda", "/kvkk", "/kunye", "/tr/iletisim"),
    "de": ("/impressum", "/kontakt", "/datenschutz", "/ueber-uns", "/de/impressum", "/de/kontakt"),
    "fr": ("/contact", "/nous-contacter", "/mentions-legales", *_INTERNATIONAL),
    "it": ("/contatti", "/contattaci", "/chi-siamo", *_INTERNATIONAL),
    "es": ("/contacto", "/aviso-legal", *_INTERNATIONAL),
    "pt": ("/contato", "/contacto", *_INTERNATIONAL),
    "nl": ("/contact", "/over-ons", *_INTERNATIONAL),
    "pl": ("/kontakt", "/o-nas", *_INTERNATIONAL),
    "cs": ("/kontakt", "/kontakty", *_INTERNATIONAL),
    "hu": ("/kapcsolat", "/impresszum", "/elerhetoseg", *_INTERNATIONAL),
    "ro": ("/contact", *_INTERNATIONAL),
    "sh": ("/kontakt", "/kontakti", *_INTERNATIONAL),
    "lt": ("/kontaktai", *_INTERNATIONAL),
    "lv": ("/kontakti", *_INTERNATIONAL),
    "et": ("/kontakt", *_INTERNATIONAL),
    "nordic": ("/kontakt", "/kontakta-oss", "/yhteystiedot", *_INTERNATIONAL),
    "ru": ("/contacts", "/kontakty", "/kontakti", "/contact", "/en/contacts", "/en/contact"),
    "el": ("/contact", "/epikoinonia", *_INTERNATIONAL),
    "he": ("/contact", "/contact-us", *_INTERNATIONAL),
    "ar": ("/contact", "/contact-us", *_INTERNATIONAL),
    "vi": ("/lien-he", "/contact", *_INTERNATIONAL),
    "id": ("/kontak", "/hubungi-kami", "/contact", *_INTERNATIONAL),
    "ko": ("/contact", "/sub/contact", *_INTERNATIONAL),
    "ja": ("/contact", "/inquiry", "/company", *_INTERNATIONAL),
    "zh": ("/contact", "/contactus", "/about/contact", *_INTERNATIONAL),
}


def guess_urls(final_url: str, languages: tuple[str, ...] = ("en", "tr", "de")) -> list[str]:
    """Common contact paths for the languages, at the site root and inside the
    folder the site redirected to (e.g. /tr/ or /de/)."""
    parts = urlsplit(final_url)
    root = f"{parts.scheme}://{parts.netloc}"
    final_url = f"{root}{parts.path or '/'}"  # drop ?ckattempt=1 and the like
    folder = final_url if final_url.endswith("/") else final_url.rsplit("/", 1)[0] + "/"
    urls: list[str] = []
    for language in languages:
        for path in _GUESS_PATHS.get(language, ()):
            candidates = [urljoin(root, path)]
            if parts.path.strip("/"):
                candidates.append(urljoin(folder, path.lstrip("/")))
            for url in candidates:
                if url not in urls:
                    urls.append(url)
    return urls


# -------------------------------------------------------------- site identity
_MULTI_PART_SUFFIXES = frozenset({
    "com.tr", "org.tr", "net.tr", "gen.tr", "biz.tr", "info.tr", "web.tr", "av.tr", "bel.tr",
    "edu.tr", "gov.tr", "k12.tr", "tv.tr", "name.tr", "tel.tr", "dr.tr", "pol.tr",
    "co.uk", "org.uk", "ac.uk", "gov.uk", "ltd.uk", "plc.uk", "me.uk",
    "co.at", "or.at", "ac.at", "gv.at", "com.de",
    "com.au", "net.au", "org.au", "co.nz", "com.br", "co.jp", "co.za", "com.cn", "com.mx",
    "co.in", "com.sg", "com.hk", "co.il", "com.cy", "com.ua", "com.pl", "co.kr",
})


def site_key(url_or_host: str) -> str:
    """The registrable domain: shop.acme.com.tr -> acme.com.tr, www.a.de -> a.de."""
    host = urlsplit(url_or_host).hostname if "://" in url_or_host else url_or_host
    labels = (host or "").lower().strip(".").split(".")
    if len(labels) >= 3 and ".".join(labels[-2:]) in _MULTI_PART_SUFFIXES:
        return ".".join(labels[-3:])
    return ".".join(labels[-2:])


def same_site(a: str, b: str) -> bool:
    key = site_key(a)
    return bool(key) and key == site_key(b)


def toggle_www(url: str) -> str:
    parts = urlsplit(url)
    host = parts.netloc
    host = host[4:] if host.lower().startswith("www.") else "www." + host
    return parts._replace(netloc=host).geturl()


# ------------------------------------------------------------ structured data
def structured_emails(soup) -> list[str]:
    """Addresses published as schema.org data (JSON-LD or microdata)."""
    found: list[str] = []

    def walk(value) -> None:
        if isinstance(value, dict):
            for key, item in value.items():
                if key.lower() == "email":
                    for email in item if isinstance(item, list) else [item]:
                        if isinstance(email, str):
                            found.append(email.removeprefix("mailto:"))
                else:
                    walk(item)
        elif isinstance(value, list):
            for item in value:
                walk(item)

    for script in soup.find_all("script", type=re.compile("ld\\+json", re.I)):
        try:
            walk(json.loads(script.string or ""))
        except (ValueError, TypeError):
            continue
    for tag in soup.find_all(attrs={"itemprop": re.compile(r"^email$", re.I)}):
        value = tag.get("content") or tag.get("href") or tag.get_text(" ", strip=True)
        if value:
            found.append(str(value).removeprefix("mailto:"))
    return found


# ------------------------------------------------------------------ sitemaps
_LOC = re.compile(r"<loc>\s*([^<\s]+)\s*</loc>", re.IGNORECASE)
_ROBOTS_SITEMAP = re.compile(r"^\s*sitemap:\s*(\S+)", re.IGNORECASE | re.MULTILINE)


def sitemaps_from_robots(text: str) -> list[str]:
    return _ROBOTS_SITEMAP.findall(text or "")


def parse_sitemap(xml: str) -> tuple[list[str], list[str]]:
    """Returns (page URLs, child sitemap URLs) from a sitemap or sitemap index."""
    locs = [loc.replace("&amp;", "&") for loc in _LOC.findall(xml or "")]
    if "<sitemapindex" in (xml or "").lower():
        return [], locs
    return locs, []


# ------------------------------------------------------------- page verdicts
PARKING_HOSTS = frozenset({
    "sedo.com", "sedoparking.com", "dan.com", "afternic.com", "hugedomains.com", "bodis.com",
    "parkingcrew.net", "above.com", "undeveloped.com", "domainmarket.com", "buydomains.com",
    "atom.com", "squadhelp.com", "sav.com", "parklogic.com", "domainnamesales.com",
    "uniregistry.com", "efty.com", "brandbucket.com",
})
_PARKED_PHRASES = re.compile(
    r"this domain (?:name )?(?:is|may be) for sale|domain (?:is )?for sale|buy this domain|"
    r"this domain (?:has been registered|is parked)|parked (?:free|domain)|"
    r"bu alan ad[ıi] sat[ıi]l[ıi]kt[ıi]r|bu alan ad[ıi] sat[ıi]l[ıi]k|alan ad[ıi] sat[ıi]l[ıi]k|"
    r"bu domain sat[ıi]l[ıi]k|diese domain (?:steht zum verkauf|kann erworben werden|ist geparkt)|"
    r"domain (?:kaufen|zu verkaufen)",
    re.IGNORECASE,
)
_CHALLENGE_MARKERS = (
    "cf-chl", "challenge-platform", "cf-browser-verification", "ddos-guard",
    "_incapsula_resource", "sucuri website firewall", "px-captcha", "perimeterx",
    "g-recaptcha", "h-captcha", "hcaptcha.com/1/api",
)
_CHALLENGE_TITLES = ("<title>just a moment", "attention required! | cloudflare", "<title>access denied")


_LANGUAGE_FOLDER = re.compile(r"^/[a-z]{2}(?:[-_][a-z]{2,4})?(?=/|$)", re.IGNORECASE)


def page_key(url: str, ignore_language: bool = False) -> str:
    """An address with scheme, ``www.``, fragment and trailing slash ignored, so the
    same page is not opened twice. With ``ignore_language``, /es/contact-us and
    /contact-us count as the same page."""
    parts = urlsplit(url)
    host = (parts.hostname or "").lower().removeprefix("www.")
    path = parts.path.rstrip("/").lower()
    if ignore_language:
        path = _LANGUAGE_FOLDER.sub("", path)
    return f"{host}{path or '/'}" + (f"?{parts.query}" if parts.query else "")


def is_parking_redirect(site_url: str, final_url: str) -> bool:
    """A redirect to another site that carries the domain as a parameter, which is how
    parking services pass the domain along (``?dn=example.com``)."""
    if same_site(site_url, final_url):
        return False
    domain = site_key(site_url)
    query = unquote(urlsplit(final_url).query).lower()
    return bool(domain) and domain in query


def is_parked(final_url: str, visible_text: str) -> bool:
    host = (urlsplit(final_url).hostname or "").lower()
    if any(host == parked or host.endswith("." + parked) for parked in PARKING_HOSTS):
        return True
    # Only short pages: a large site mentioning "domain for sale" in an article is not parked.
    return len(visible_text) < 4000 and bool(_PARKED_PHRASES.search(visible_text))


def is_blocked(status: int, html: str) -> bool:
    """A bot-protection or captcha page instead of the real site.

    Captcha scripts alone are not enough (many contact forms use reCAPTCHA); the
    server must also refuse the request, or the page must be a challenge page.
    """
    head = (html or "")[:20000].lower()
    if status == 429 or any(title in head for title in _CHALLENGE_TITLES):
        return True
    return status in (403, 503) and any(marker in head for marker in _CHALLENGE_MARKERS)


def has_contact_form(soup) -> bool:
    for form in soup.find_all("form"):
        names = " ".join(
            str(field.get("name", "")) + " " + str(field.get("type", ""))
            for field in form.find_all(["input", "textarea"])
        ).lower()
        searchy = re.search(r"\b(q|s|search|query|arama|suche)\b", names)
        if form.find("textarea") and not searchy:
            return True
        if "email" in names and ("message" in names or "mesaj" in names or "nachricht" in names):
            return True
    return False


@dataclass
class PageLink:
    url: str
    score: int
