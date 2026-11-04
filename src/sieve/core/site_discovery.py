"""Understanding a website well enough to find where its contact details are.

Pure functions, no network: language detection, ranking links that lead to
contact/legal pages in English, Turkish and German, reading schema.org data,
parsing sitemaps and recognising parked domains, bot-protection pages and
contact forms.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from urllib.parse import unquote, urljoin, urlsplit

LANGUAGES = ("en", "tr", "de")

# --------------------------------------------------------------- page scoring
# (pattern, score). Patterns are matched against folded text: lower case,
# Turkish and German letters replaced by ASCII, separators turned into spaces.
# A page that legally or by convention carries an email address scores highest.
_RULES: dict[str, list[tuple[str, int]]] = {
    "en": [
        (r"contact(?: us)?|get in touch|reach us|write to us|contact information", 100),
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
}
_NEGATIVE = re.compile(
    r"\b(products?|shop|store|cart|basket|checkout|category|categories|blog|news|article|"
    r"login|log in|register|sign up|account|careers?|jobs?|"
    r"urun(?:ler)?|sepet|kategori|haber(?:ler)?|giris|uye ol|kariyer|"
    r"produkte?|warenkorb|kategorie|aktuelles|anmelden|registrieren|karriere|stellen)\b"
)
_FILE_LINK = re.compile(r"\.(?:pdf|jpe?g|png|gif|webp|svg|zip|rar|docx?|xlsx?|pptx?|mp4|mp3)(?:$|[?#])", re.I)

_COMPILED = {
    language: [(re.compile(rf"\b(?:{pattern})\b"), score) for pattern, score in rules]
    for language, rules in _RULES.items()
}

_FOLD = str.maketrans({
    "ı": "i", "İ": "i", "ş": "s", "Ş": "s", "ç": "c", "Ç": "c", "ğ": "g", "Ğ": "g",
    "ö": "o", "Ö": "o", "ü": "u", "Ü": "u", "ä": "a", "Ä": "a", "ß": "ss", "â": "a", "î": "i",
})


def fold(text: str) -> str:
    """Lower-case, map Turkish/German letters to ASCII, turn separators into spaces."""
    text = unquote(text).translate(_FOLD).lower()
    return re.sub(r"[\s/_\-.+%]+", " ", text).strip()


def score_link(href: str, text: str, languages: tuple[str, ...]) -> int:
    """How likely the link leads to a page with contact details (0 = not at all)."""
    if _FILE_LINK.search(href):
        return 0
    path = urlsplit(href).path
    folded_path, folded_text = fold(path), fold(text)
    best = 0
    for language in languages:
        for pattern, score in _COMPILED.get(language, ()):
            in_text = bool(pattern.search(folded_text))
            in_path = bool(pattern.search(folded_path))
            if in_text or in_path:
                best = max(best, score + (10 if in_text and in_path else 0))
    if best and (_NEGATIVE.search(folded_path) or _NEGATIVE.search(folded_text)):
        best -= 90
    return max(best, 0)


# ------------------------------------------------------------------ language
_TLD_LANGUAGE = {"tr": "tr", "de": "de", "at": "de", "ch": "de", "li": "de"}


# Letters are matched case-sensitively: with IGNORECASE, "ı" would also match "I".
_TR_HINT = re.compile(r"[şğıŞĞİ]|\b(?:ve|ile|için|hakkımızda|iletişim|ürünler)\b")
_DE_HINT = re.compile(r"[äßÄ]|\b(?:und|der|die|das|für|über uns|Impressum|Kontakt)\b")


def detect_languages(html_lang: str | None, url: str, text: str = "") -> tuple[str, ...]:
    """Languages of the site, most likely first; English is always included.

    Uses the page's declared language, then the country ending of the domain,
    then a quick look at the text.
    """
    found: list[str] = []
    code = (html_lang or "").strip().lower()[:2]
    if code in LANGUAGES:
        found.append(code)
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


_GUESS_PATHS = {
    "en": ("/contact", "/contact-us", "/about", "/about-us", "/imprint", "/legal", "/privacy-policy"),
    "tr": ("/iletisim", "/bize-ulasin", "/hakkimizda", "/kvkk", "/kunye", "/tr/iletisim"),
    "de": ("/impressum", "/kontakt", "/datenschutz", "/ueber-uns", "/de/impressum", "/de/kontakt"),
}


def guess_urls(final_url: str, languages: tuple[str, ...] = LANGUAGES) -> list[str]:
    """Common contact paths for the languages, at the site root and inside the
    folder the site redirected to (e.g. /tr/ or /de/)."""
    parts = urlsplit(final_url)
    root = f"{parts.scheme}://{parts.netloc}"
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
