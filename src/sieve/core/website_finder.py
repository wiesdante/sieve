"""Find companies' own websites by searching their names on DuckDuckGo.

For every company name the finder:

1. searches DuckDuckGo (its plain HTML page, with the "lite" page as a fallback),
   skipping ads and recognising when DuckDuckGo answers with a bot check or a rate
   limit instead of results, so a blocked search is never mistaken for "no website",
2. drops results that are not a company's own site: social networks, marketplaces,
   business directories, encyclopedias and news, job sites, maps and review sites,
   website-builder profiles (``name.wixsite.com``), files, and your own block list,
3. checks that a result belongs to *this* company: the domain must be made of the
   company's name (legal endings such as Ltd., A.Ş. or GmbH ignored), its initials,
   or the start of its words (``Bird Aerosystems`` -> ``birdaero.com``); or the page
   title names the company and the address is the site's home page,
4. reports the site's home page. Close but uncertain candidates are reported as
   *Unsure* and never mixed into the list of websites.

Searches are spread over the proxies from Settings, each resting between uses; a
proxy that is rate limited rests longer and a proxy that keeps failing is dropped.
"""

from __future__ import annotations

import random
import re
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from urllib.parse import parse_qs, urlencode, urlsplit

from sieve.core.parallel import run_parallel
from sieve.core.site_discovery import site_key, strip_accents

# ------------------------------------------------------------------ statuses
FOUND = "found"
UNSURE = "unsure"
NO_SITE = "no_site"
RATE_LIMITED = "rate_limited"
FAILED = "failed"
STATUSES = (FOUND, UNSURE, NO_SITE, RATE_LIMITED, FAILED)

#: How a result matched the company.
MATCH_DOMAIN = "domain"
MATCH_TITLE = "title"

RESULT_LIMIT = 10
ATTEMPTS = 3
#: Rest between two searches through the same proxy, and without proxies.
PROXY_COOLDOWN = 10.0
DIRECT_COOLDOWN = 6.0
#: Rest after DuckDuckGo rate limited a proxy (or the direct connection); doubles each
#: time in a row, up to MAX_PENALTY.
LIMIT_PENALTY = 30.0
DIRECT_LIMIT_PENALTY = 45.0
MAX_PENALTY = 240.0
#: When every connection has been limited this many times in a row, the remaining
#: companies are reported as rate limited instead of waiting on (Retry failed later).
GIVE_UP_AFTER_LIMITS = 3
#: A proxy that fails this many times in a row is dropped for the rest of the run.
DEAD_AFTER = 3
COMPANY_HARD_LIMIT = 900.0

HTML_ENDPOINT = "https://html.duckduckgo.com/html/"
#: Answers that mean the browser itself cannot run, so every search would fail.
BROWSER_MISSING = "Browser not available"
LITE_ENDPOINT = "https://lite.duckduckgo.com/lite/"

#: DuckDuckGo regions ("kl" parameter). "" searches all regions.
REGIONS = (
    ("", "All regions"), ("tr-tr", "Turkey"), ("us-en", "United States"), ("uk-en", "United Kingdom"),
    ("de-de", "Germany"), ("fr-fr", "France"), ("it-it", "Italy"), ("es-es", "Spain"),
    ("nl-nl", "Netherlands"), ("pl-pl", "Poland"), ("cz-cs", "Czech Republic"), ("ru-ru", "Russia"),
    ("ua-uk", "Ukraine"), ("il-he", "Israel"), ("xa-ar", "Arabia"), ("in-en", "India"),
    ("cn-zh", "China"), ("jp-jp", "Japan"), ("kr-kr", "Korea"), ("br-pt", "Brazil"),
)


# --------------------------------------------------------- non-company sites
@dataclass(frozen=True)
class Category:
    title: str
    description: str
    #: Domains matched with their subdomains (m.facebook.com, tr.linkedin.com).
    domains: frozenset[str]
    #: Brand names matched with any ending (amazon.de, amazon.com.tr).
    brands: frozenset[str] = frozenset()


def _set(text: str) -> frozenset[str]:
    return frozenset(text.split())


CATEGORIES: dict[str, Category] = {
    "social": Category(
        "Social media and video",
        "Facebook, Instagram, LinkedIn, X, YouTube, TikTok, GitHub, Medium and similar.",
        _set("""facebook.com fb.com fb.me instagram.com twitter.com x.com t.co linkedin.com lnkd.in
        youtube.com youtu.be tiktok.com pinterest.com pin.it reddit.com tumblr.com threads.net vk.com
        ok.ru telegram.me t.me snapchat.com weibo.com quora.com medium.com discord.com discord.gg
        twitch.tv vimeo.com dailymotion.com flickr.com behance.net dribbble.com soundcloud.com
        spotify.com github.com gitlab.com bsky.app mastodon.social xing.com line.me whatsapp.com
        wa.me messenger.com slideshare.net scribd.com issuu.com calameo.com"""),
    ),
    "marketplace": Category(
        "Marketplaces and shops",
        "Amazon, eBay, Alibaba, Trendyol, Hepsiburada, n11, Etsy, Shopier and similar.",
        _set("""made-in-china.com indiamart.com globalsources.com tradeindia.com exportersindia.com
        tradekey.com ec21.com ecplaza.net go4worldbusiness.com dhgate.com 1688.com"""),
        _set("""amazon ebay etsy alibaba aliexpress trendyol hepsiburada n11 ciceksepeti sahibinden
        shopier temu walmart rakuten mercadolibre mercadolivre allegro ozon wildberries avito
        gittigidiyor akakce cimri epey letgo dolap pazarama idefix"""),
    ),
    "directory": Category(
        "Business directories and company data",
        "Kompass, Europages, ZoomInfo, Crunchbase, Dun & Bradstreet, yellow pages, Turkish "
        "company directories and similar.",
        _set("""kompass.com europages.com europages.co.uk zoominfo.com crunchbase.com dnb.com
        opencorporates.com bizapedia.com manta.com hotfrog.com cylex.com cylex.com.tr tuugo.com
        infobel.com bbb.org owler.com cbinsights.com pitchbook.com tracxn.com apollo.io
        rocketreach.co signalhire.com lusha.com emis.com northdata.com northdata.de
        firmenwissen.de companieshouse.gov.uk company-information.service.gov.uk endole.co.uk
        companycheck.co.uk globaldatabase.com b2bhint.com thomasnet.com kellysearch.com
        yellowpages.com yell.com goldenpages.ie gelbeseiten.de dasoertliche.de pagesjaunes.fr
        paginegialle.it paginasamarillas.es firmy.cz zlatestranky.cz panoramafirm.pl
        bulurum.com firmasec.com firmarehberi.com.tr rehberim.com sirketler.web.tr
        ticaretsicil.gov.tr ihracatbilgi.com turkishexporter.com.tr exporthub.com
        companiesmarketcap.com marketscreener.com zaubacorp.com tofler.in dnb.co.in
        corporationwiki.com buzzfile.com chamberofcommerce.com mapquest.com cybo.com
        yably.com yasabe.com find-us-here.com brownbook.net"""),
        _set("kompass europages yellowpages zoominfo crunchbase opencorporates cylex infobel"),
    ),
    "reference": Category(
        "Encyclopedias, news and finance",
        "Wikipedia, news sites, press-release services, stock and finance pages.",
        _set("""wikipedia.org wikiwand.com wikidata.org wikimedia.org britannica.com fandom.com
        reuters.com bloomberg.com forbes.com cnbc.com bbc.com bbc.co.uk cnn.com nytimes.com
        theguardian.com ft.com wsj.com apnews.com businesswire.com prnewswire.com globenewswire.com
        accesswire.com einpresswire.com finance.yahoo.com news.yahoo.com investing.com
        macrotrends.net statista.com sec.gov marketwatch.com seekingalpha.com barrons.com
        tradingview.com fool.com zacks.com simplywall.st companiesmarketcap.com stockanalysis.com morningstar.com hurriyet.com.tr
        milliyet.com.tr sabah.com.tr haberturk.com ntv.com.tr cnnturk.com sozcu.com.tr aa.com.tr
        dunya.com bloomberght.com ekonomim.com defensenews.com janes.com armyrecognition.com
        defence-blog.com militaryleak.com defenseworld.net army-technology.com
        airforce-technology.com naval-technology.com globalsecurity.org"""),
    ),
    "jobs": Category(
        "Job sites and company reviews",
        "Indeed, Glassdoor, Kariyer.net, Yenibiris, Monster, StepStone and similar.",
        _set("""indeed.com glassdoor.com glassdoor.co.uk kariyer.net yenibiris.com secretcv.com
        eleman.net monster.com stepstone.de careerjet.com adzuna.com simplyhired.com
        ziprecruiter.com comparably.com kununu.com jobs.ch"""),
        _set("indeed glassdoor monster stepstone"),
    ),
    "maps": Category(
        "Maps, reviews and travel",
        "Google Maps, Yandex Maps, Yelp, Tripadvisor, Foursquare, Trustpilot, Şikayetvar, "
        "booking sites and similar.",
        _set("""maps.google.com maps.app.goo.gl goo.gl yandex.com.tr yandex.ru 2gis.com 2gis.ru
        foursquare.com yelp.com tripadvisor.com trustpilot.com sikayetvar.com waze.com wego.here.com
        booking.com expedia.com hotels.com agoda.com trivago.com apps.apple.com play.google.com"""),
        _set("tripadvisor yelp trustpilot booking"),
    ),
    "builder": Category(
        "Website-builder and hosting profiles",
        "Pages under someone else's domain: name.wixsite.com, name.blogspot.com, "
        "name.business.site, sites.google.com, name.github.io and similar.",
        _set("""wixsite.com weebly.com blogspot.com blogger.com wordpress.com business.site
        godaddysites.com square.site webflow.io carrd.co jimdo.com jimdosite.com strikingly.com
        mystrikingly.com site123.me yolasite.com tilda.ws sites.google.com notion.site
        framer.website github.io netlify.app vercel.app herokuapp.com firebaseapp.com web.app
        pages.dev myshopify.com ueniweb.com wixstudio.io webnode.page webnode.com.tr"""),
    ),
}

_FILE = re.compile(r"\.(?:pdf|docx?|xlsx?|pptx?|zip|rar|jpe?g|png|gif|mp4)$", re.IGNORECASE)


def host_of(url: str) -> str:
    return (urlsplit(url).hostname or "").lower().removeprefix("www.")


def _in_domains(host: str, domains: frozenset[str]) -> bool:
    return any(host == domain or host.endswith("." + domain) for domain in domains)


def brand_label(host: str) -> str:
    """The name part of a host: www.acme.com.tr -> acme, mod.gov.sk -> mod."""
    return site_key(host).split(".")[0]


def parse_block_rules(text: str) -> list[str]:
    """Your own block list: a domain per line (with its subdomains), or any text the
    address must not contain. ``#`` starts a note."""
    rules: list[str] = []
    for line in (text or "").splitlines():
        rule = line.split("#", 1)[0].strip().lower()
        if rule.startswith(("http://", "https://")):
            rule = rule.split("://", 1)[1]
        rule = rule.removeprefix("www.")
        if rule.count("/") == 1 and rule.endswith("/") and "." in rule:
            rule = rule[:-1]  # "firmabul.com/" is a domain
        if rule and rule not in rules:
            rules.append(rule)
    return rules


@dataclass
class FinderSettings:
    region: str = ""
    #: Category keys that are skipped (all by default).
    categories: frozenset[str] = frozenset(CATEGORIES)
    block: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {"region": self.region, "categories": sorted(self.categories)}

    @classmethod
    def from_dict(cls, data: dict) -> FinderSettings:
        region = data.get("region", "")
        categories = data.get("categories")
        return cls(
            region=region if region in dict(REGIONS) else "",
            categories=frozenset(c for c in categories if c in CATEGORIES)
            if isinstance(categories, list) else frozenset(CATEGORIES),
        )


def not_a_company_site(
    url: str, settings: FinderSettings, company_label: str | tuple[str, ...] = ""
) -> str | None:
    """Why the address cannot be a company's own website, or None."""
    parts = urlsplit(url)
    if parts.scheme not in ("http", "https") or not parts.hostname:
        return "Not a web address"
    host = host_of(url)
    if _FILE.search(parts.path):
        return "A file, not a website"
    lowered = url.lower()
    for rule in settings.block:
        if ("/" not in rule and "." in rule and " " not in rule and _in_domains(host, frozenset({rule}))) or (
            rule in lowered
        ):
            return f"Your block list: {rule}"
    label = re.sub(r"[^a-z0-9]", "", brand_label(host))
    labels = (company_label,) if isinstance(company_label, str) else company_label
    if label and label in labels:
        # The company is the platform itself: "Trendyol", or "Army Recognition Group" whose
        # own site is a news site.
        return None
    for key in settings.categories:
        category = CATEGORIES[key]
        if _in_domains(host, category.domains) or label in category.brands:
            return category.title
    return None


# ------------------------------------------------------------ name matching
#: Legal forms and filler words that are not part of a company's name.
_LEGAL = _set("""ltd limited sti sirketi sirket as anonim ve and the of und et y e di de du der
inc incorporated corp corporation co company llc llp lp gmbh mbh ag kg ohg ug se sa sas sarl srl
spa sl bv nv oy oyj ab aps plc pty pvt private sanayi sanayii san tic ticaret ith ihr ithalat
ihracat pazarlama paz koll kollektif mahdut sirketler grubu kft zrt nyrt doo dd ad ooo oao zao pjsc
jsc jsco ojsc cjsc pjsco kk sdn bhd tbk pte cv""")
#: Common words that alone do not identify a company.
_GENERIC = _set("""group grup holding international intl global industries industry industrial
technologies technology tech teknoloji systems system sistem sistemleri solutions solution
services service hizmetleri defence defense savunma aerospace havacilik engineering muhendislik
trading export import makina makine makinalari elektronik electronics energy enerji insaat
construction products urunleri manufacturing uretim imalat consulting danismanlik logistics
lojistik security guvenlik software yazilim digital media medya design tasarim systeme""")
#: Extra words often added to a company's domain.
#: Country words are left out on purpose: arsenal-usa.com is not Bulgaria's Arsenal JSCo.
_DOMAIN_FILLERS = ("group", "grup", "global", "intl", "international", "official", "online", "web",
                   "corp", "inc", "ltd", "hq", "the", "my", "get", "go", "co")
_HOME_SLUGS = _set("""home index default main anasayfa startseite accueil inicio inizio
homepage portal welcome""")
_LANGUAGE_SLUG = re.compile(r"^[a-z]{2}(?:[-_][a-z]{2})?$")
_PAGE_EXTENSIONS = (".html", ".htm", ".php", ".aspx", ".asp", ".jsp")


@dataclass(frozen=True)
class CompanyName:
    raw: str
    #: Name words without legal forms, folded to plain letters.
    tokens: tuple[str, ...]
    #: Words that identify the company (generic words left out when others exist).
    distinctive: tuple[str, ...]

    @property
    def joined(self) -> str:
        return "".join(self.tokens)

    @property
    def initials(self) -> str:
        return "".join(token[0] for token in self.tokens) if len(self.tokens) >= 2 else ""

    @property
    def label(self) -> tuple[str, ...]:
        """Domain names that are this company's own, even on a listed platform."""
        return tuple(dict.fromkeys(filter(None, (self.joined, "".join(self.distinctive)))))


def company_name(raw: str) -> CompanyName:
    text = strip_accents(raw).replace("&", " and ")
    words = re.findall(r"[a-z0-9]+", text)
    tokens = [word for word in words if word not in _LEGAL and len(word) > 1 or word.isdigit()]
    if not tokens:
        tokens = [word for word in words if len(word) > 1] or words
    distinctive = [token for token in tokens if token not in _GENERIC] or tokens
    return CompanyName(raw.strip(), tuple(tokens), tuple(distinctive))


def _coverage(label: str, name: CompanyName) -> tuple[float, int, bool]:
    """How much of the domain label is spelled by the name: (share of the label covered,
    letters covered by distinctive words, whether the name's leading word is in it)."""
    covered = [False] * len(label)
    distinctive_letters = 0
    lead = name.distinctive[0] if name.distinctive else ""
    has_lead = False
    pieces: list[tuple[str, bool]] = []
    for token in name.tokens:
        # Whole words, and their starts ("aero" from "aerosystems"), longest first.
        prefixes = [token[:size] for size in range(len(token), 2, -1)] if len(token) > 3 else [token]
        pieces.extend((prefix, token in name.distinctive) for prefix in prefixes)
    if name.initials and len(name.initials) >= 2:
        pieces.append((name.initials, True))
    pieces.extend((filler, False) for filler in _DOMAIN_FILLERS)
    pieces.sort(key=lambda piece: -len(piece[0]))
    for piece, is_distinctive in pieces:
        start = label.find(piece)
        while start != -1:
            span = range(start, start + len(piece))
            if not any(covered[i] for i in span):
                for i in span:
                    covered[i] = True
                if is_distinctive:
                    distinctive_letters += len(piece)
                if piece == name.initials or (lead and lead.startswith(piece) and len(piece) >= min(3, len(lead))):
                    has_lead = True
                break
            start = label.find(piece, start + 1)
    share = sum(covered) / len(label) if label else 0.0
    return share, distinctive_letters, has_lead


def domain_match(url: str, name: CompanyName) -> str | None:
    """"domain" when the domain is spelled by the company's name, "partial" when it is
    only close, None when it is unrelated."""
    label = re.sub(r"[^a-z0-9]", "", brand_label(host_of(url)))
    if not label or not name.tokens:
        return None
    if label in (name.joined, "".join(name.distinctive), name.initials):
        return MATCH_DOMAIN
    share, distinctive_letters, has_lead = _coverage(label, name)
    # The leading word is usually the brand: "Bird Aerosystems" is not aerosystems.com.
    if share >= 0.8 and distinctive_letters >= min(3, len(label)) and has_lead:
        return MATCH_DOMAIN
    longest = max(name.distinctive, key=len)
    close = SequenceMatcher(None, label, "".join(name.distinctive)).ratio() >= 0.75
    if (share >= 0.4 and distinctive_letters >= 4) or (len(longest) >= 4 and longest in label) or close:
        return "partial"
    return None


def title_names_company(title: str, name: CompanyName) -> bool:
    folded = " ".join(re.findall(r"[a-z0-9]+", strip_accents(title)))
    compact = folded.replace(" ", "")
    words = set(folded.split())
    # Every word of the name, not just the distinctive ones: "Acme Tools" does not name
    # "Acme Savunma".
    wanted = name.tokens[:4]
    if not wanted:
        return False
    if all(token in words or (len(token) >= 5 and token in compact) for token in wanted):
        return True
    return len(name.joined) >= 5 and name.joined in compact


def is_home_page(url: str) -> bool:
    """The site's home page, a language version of it, or a generic first page."""
    parts = urlsplit(url)
    if parts.query and not re.fullmatch(r"(?:(?:lang|hl|language|locale)=[\w-]+&?)+", parts.query):
        return False
    segments = [segment.lower() for segment in parts.path.split("/") if segment]
    if len(segments) > 2:
        return False
    for segment in segments:
        for extension in _PAGE_EXTENSIONS:
            segment = segment.removesuffix(extension)
        if segment not in _HOME_SLUGS and not _LANGUAGE_SLUG.match(segment):
            return False
    return True


def home_page(url: str) -> str:
    parts = urlsplit(url)
    return f"{parts.scheme}://{parts.netloc.lower()}/"


def has_profile_subdomain(url: str) -> bool:
    """name.platform.com: a subdomain other than www in front of the registrable domain."""
    host = (urlsplit(url).hostname or "").lower().removeprefix("www.")
    return host != site_key(host)


# -------------------------------------------------------------- the search
@dataclass
class SearchResult:
    url: str
    title: str
    snippet: str = ""


@dataclass
class SearchPage:
    #: "results", "no_results", "limited" (bot check / rate limit) or "unexpected".
    kind: str
    results: list[SearchResult] = field(default_factory=list)
    detail: str = ""


_LIMIT_MARKERS = (
    "anomaly-modal", "anomaly_modal", "anomaly.js", "challenge-form", "bots use duckduckgo too",
    "please complete the following challenge", "confirm this search was made by a human",
    "if this persists, please", "ddg-captcha",
)


def _real_url(href: str) -> str:
    href = (href or "").strip()
    if href.startswith("//"):
        href = "https:" + href
    parts = urlsplit(href)
    if "duckduckgo.com" in (parts.hostname or "") and parts.path.startswith("/l/"):
        target = parse_qs(parts.query).get("uddg")
        if target:
            return target[0]
    return href


def _is_ad(href: str, classes: list[str]) -> bool:
    if any(cls in ("result--ad", "result--ad--small", "result-sponsored") for cls in classes):
        return True
    host = urlsplit(href if "://" in href else "https:" + href).hostname or ""
    return "duckduckgo.com" in host and "/y.js" in href


def parse_search_page(status: int, html: str) -> SearchPage:
    """Read a DuckDuckGo HTML or lite results page."""
    from bs4 import BeautifulSoup

    lowered = (html or "").lower()
    if status in (202, 403, 418, 429) or any(marker in lowered for marker in _LIMIT_MARKERS):
        return SearchPage("limited", detail=f"DuckDuckGo asked to slow down (HTTP {status})")
    if status != 200:
        return SearchPage("unexpected", detail=f"DuckDuckGo answered HTTP {status}")
    soup = BeautifulSoup(html, "html.parser")
    results: list[SearchResult] = []
    seen: set[str] = set()

    # html.duckduckgo.com
    for block in soup.select("div.result, div.web-result"):
        link = block.select_one("a.result__a")
        if link is None:
            continue
        href = link.get("href") or ""
        if _is_ad(href, block.get("class") or []):
            continue
        url = _real_url(href)
        snippet = block.select_one(".result__snippet")
        _add(results, seen, url, link.get_text(" ", strip=True), snippet.get_text(" ", strip=True) if snippet else "")

    # lite.duckduckgo.com: results are table rows; sponsored rows are marked.
    if not results:
        for link in soup.select("a.result-link"):
            row = link.find_parent("tr")
            classes = row.get("class") or [] if row else []
            href = link.get("href") or ""
            if _is_ad(href, classes):
                continue
            snippet_row = row.find_next_sibling("tr") if row else None
            snippet = snippet_row.select_one(".result-snippet") if snippet_row else None
            _add(results, seen, _real_url(href), link.get_text(" ", strip=True),
                 snippet.get_text(" ", strip=True) if snippet else "")

    if results:
        return SearchPage("results", results[:RESULT_LIMIT])
    # Only DuckDuckGo's own "No results" note counts as an empty search; any other page
    # without results (a new layout, a check page) is retried rather than read as "no website".
    if soup.select_one(".no-results") or re.search(r"\bno\s+results\b", lowered):
        return SearchPage("no_results")
    return SearchPage("unexpected", detail="DuckDuckGo answered with a page that has no results list")


def _add(results: list[SearchResult], seen: set[str], url: str, title: str, snippet: str) -> None:
    if url.startswith(("http://", "https://")) and url not in seen:
        seen.add(url)
        results.append(SearchResult(url, title, snippet))


class BrowserSearcher:
    """Searches through the real browser (Chrome or Edge), with one connection's proxy.

    DuckDuckGo turns down plain HTTP clients at once (HTTP 202), even from home
    connections, while a real browser gets results; the browser also keeps this
    connection's cookies from search to search, like a person searching.
    """

    def __init__(self, fetcher) -> None:
        self._fetcher = fetcher

    def search(self, query: str, region: str = "", lite: bool = False) -> tuple[SearchPage, str | None]:
        """(page, connection error)."""
        endpoint = LITE_ENDPOINT if lite else HTML_ENDPOINT
        url = endpoint + "?" + urlencode({"q": query, "kl": region or "wt-wt"})
        result = self._fetcher.fetch(url, quick=True)
        if result.error or result.text is None:
            return SearchPage("unexpected"), result.error or "No answer"
        return parse_search_page(result.status, result.text), None


# ------------------------------------------------------------- run status
class RunStatus:
    """What the run is doing right now, for the window to show while it waits."""

    def __init__(self) -> None:
        self._text = ""
        self._lock = threading.Lock()

    @property
    def text(self) -> str:
        with self._lock:
            return self._text

    def set(self, text: str) -> None:
        with self._lock:
            self._text = text


# ------------------------------------------------------------- connections
class Connections:
    """The proxies (or the direct connection) searches go through, with rest periods."""

    def __init__(
        self,
        proxies: list | None,
        searcher_for: Callable[[object | None], object],
        status: RunStatus | None = None,
    ) -> None:
        self.using_proxies = bool(proxies)
        self.status = status or RunStatus()
        self._last_limited = False
        entries = list(proxies) if proxies else [None]
        self._searchers = [searcher_for(entry) for entry in entries]
        self._names = [str(entry) if entry is not None else "direct" for entry in entries]
        self._ready_at = [0.0] * len(entries)
        self._busy = [False] * len(entries)
        self._failures = [0] * len(entries)
        self._dead = [False] * len(entries)
        self._limits = [0] * len(entries)
        #: DuckDuckGo keeps limiting every connection; the run should stop searching.
        self.exhausted = False
        self._cooldown = PROXY_COOLDOWN if proxies else DIRECT_COOLDOWN
        self._penalty = LIMIT_PENALTY if proxies else DIRECT_LIMIT_PENALTY
        self._lock = threading.Condition()

    def __len__(self) -> int:
        return len(self._searchers)

    def alive(self) -> int:
        return sum(not dead for dead in self._dead)

    def acquire(
        self, cancelled: Callable[[], bool] | None = None, avoid: set[int] | frozenset[int] = frozenset()
    ) -> int | None:
        """Wait for a rested connection; None when stopped or every proxy is dead.

        Connections in ``avoid`` (the ones that just failed this search) are only used
        when no other connection is left.
        """
        with self._lock:
            while True:
                if cancelled and cancelled():
                    return None
                if all(self._dead) or self.exhausted:
                    return None
                now = time.monotonic()
                others_alive = any(not self._dead[i] and i not in avoid for i in range(len(self._searchers)))
                ready = [i for i in range(len(self._searchers))
                         if not self._dead[i] and not self._busy[i] and self._ready_at[i] <= now
                         and (i not in avoid or not others_alive)]
                if ready:
                    chosen = random.choice(ready)
                    self._busy[chosen] = True
                    return chosen
                waits = [self._ready_at[i] - now for i in range(len(self._searchers))
                         if not self._dead[i] and not self._busy[i]]
                if waits and not any(self._busy):
                    seconds = max(1, int(min(waits) + 0.99))
                    if self._last_limited:
                        self.status.set(f"DuckDuckGo asked to slow down · waiting {seconds}s before the next search")
                    elif seconds >= 2:
                        what = "a proxy" if self.using_proxies else "the connection"
                        self.status.set(f"Waiting {seconds}s for {what} to rest")
                self._lock.wait(timeout=min([0.25, *[max(w, 0.01) for w in waits]]))

    def searcher(self, slot: int):
        return self._searchers[slot]

    def name(self, slot: int) -> str:
        return self._names[slot]

    def release(self, slot: int, outcome: str) -> None:
        """``outcome``: "ok", "limited" or "error"."""
        with self._lock:
            self._busy[slot] = False
            jitter = random.uniform(0.85, 1.35)
            self._last_limited = outcome == "limited"
            if outcome == "limited":
                self._failures[slot] = 0
                self._limits[slot] += 1
                penalty = min(self._penalty * 2 ** (self._limits[slot] - 1), MAX_PENALTY)
                self._ready_at[slot] = time.monotonic() + penalty * jitter
                alive = [i for i in range(len(self._searchers)) if not self._dead[i]]
                if alive and all(self._limits[i] >= GIVE_UP_AFTER_LIMITS for i in alive):
                    self.exhausted = True
            elif outcome == "error":
                self._failures[slot] += 1
                self._ready_at[slot] = time.monotonic() + self._cooldown * jitter
                if self.using_proxies and self._failures[slot] >= DEAD_AFTER:
                    self._dead[slot] = True
            else:
                self._failures[slot] = 0
                self._limits[slot] = 0
                self._ready_at[slot] = time.monotonic() + self._cooldown * jitter
            self._lock.notify_all()


# --------------------------------------------------------------- one company
@dataclass
class Candidate:
    url: str
    title: str
    rank: int
    #: "found", "unsure" or "skipped"
    verdict: str
    reason: str


@dataclass
class FinderResult:
    company: str
    status: str = NO_SITE
    website: str = ""
    found_url: str = ""
    title: str = ""
    rank: int = 0
    #: Why the site was accepted, e.g. "Domain matches the name".
    match: str = ""
    candidates: list[Candidate] = field(default_factory=list)
    error: str = ""
    searches: int = 0
    elapsed: float = 0.0
    log: list[str] = field(default_factory=list)


@dataclass
class FinderSummary:
    results: list[FinderResult] = field(default_factory=list)
    stopped: bool = False


MATCH_LABELS = {
    MATCH_DOMAIN: "Domain matches the name",
    MATCH_TITLE: "Page title names the company",
}


def judge_results(company: str, results: list[SearchResult], settings: FinderSettings) -> FinderResult:
    """Pick the company's own website from search results (no network)."""
    outcome = FinderResult(company)
    name = company_name(company)
    domain_pick: tuple[int, SearchResult] | None = None
    title_pick: tuple[int, SearchResult] | None = None
    unsure_pick: tuple[int, SearchResult, str] | None = None
    for rank, result in enumerate(results[:RESULT_LIMIT], start=1):
        reason = not_a_company_site(result.url, settings, name.label)
        if reason:
            outcome.candidates.append(Candidate(result.url, result.title, rank, "skipped", reason))
            continue
        match = domain_match(result.url, name)
        if match == MATCH_DOMAIN:
            outcome.candidates.append(Candidate(result.url, result.title, rank, "found", MATCH_LABELS[match]))
            domain_pick = domain_pick or (rank, result)
            continue
        names_company = title_names_company(result.title, name)
        if names_company and is_home_page(result.url) and not has_profile_subdomain(result.url):
            outcome.candidates.append(
                Candidate(result.url, result.title, rank, "found", MATCH_LABELS[MATCH_TITLE])
            )
            title_pick = title_pick or (rank, result)
            continue
        if match == "partial" or names_company:
            why = "Domain is close to the name" if match == "partial" else "Title names the company, deep page"
            outcome.candidates.append(Candidate(result.url, result.title, rank, "unsure", why))
            unsure_pick = unsure_pick or (rank, result, why)
            continue
        outcome.candidates.append(Candidate(result.url, result.title, rank, "skipped", "Does not match the name"))

    pick = domain_pick or title_pick
    if pick:
        rank, result = pick
        outcome.status = FOUND
        outcome.match = MATCH_LABELS[MATCH_DOMAIN if pick is domain_pick else MATCH_TITLE]
    elif unsure_pick:
        rank, result, why = unsure_pick
        outcome.status = UNSURE
        outcome.match = why
    else:
        outcome.status = NO_SITE
        outcome.error = "No result is the company's own site" if results else "DuckDuckGo found nothing"
        return outcome
    outcome.website = home_page(result.url)
    outcome.found_url = result.url
    outcome.title = result.title
    outcome.rank = rank
    return outcome


def find_website(
    company: str,
    connections: Connections,
    settings: FinderSettings,
    cancelled: Callable[[], bool] | None = None,
) -> FinderResult:
    started = time.monotonic()
    logs: list[str] = []

    def log(level: str, message: str) -> None:
        logs.append(f"[{time.strftime('%H:%M:%S')}] {level:<7} {message}")

    log("INFO", f"Searching: {company}")
    last_problem = ""
    limited = False
    searches = 0
    tried: set[int] = set()
    for attempt in range(ATTEMPTS):
        slot = connections.acquire(cancelled, avoid=tried)
        if slot is None:
            if cancelled and cancelled():
                last_problem = last_problem or "Stopped"
            elif connections.exhausted:
                limited = True
                last_problem = ("DuckDuckGo keeps limiting every connection; retry later"
                                + ("" if connections.using_proxies else " or turn on proxies"))
            else:
                last_problem = "Every proxy failed; check the proxy list in Settings"
            break
        tried.add(slot)
        lite = attempt % 2 == 1  # alternate with the lite page after a failed try
        via = connections.name(slot)
        connections.status.set(f"Searching: {company}" + (f" (try {attempt + 1})" if attempt else ""))
        query = " ".join(company.replace('"', " ").split())
        page, error = connections.searcher(slot).search(query, settings.region, lite=lite)
        searches += 1
        where = f"{'lite' if lite else 'html'} page via {via}"
        if error and error.startswith(BROWSER_MISSING):
            connections.release(slot, "ok")
            last_problem = "Website Finder needs Google Chrome or Microsoft Edge: " + error
            break
        if error:
            connections.release(slot, "error")
            last_problem = error
            log("WARN", f"{error} ({where})")
            continue
        if page.kind == "limited":
            connections.release(slot, "limited")
            limited = True
            last_problem = page.detail
            log("WARN", f"{page.detail} ({where}); trying again later")
            continue
        if page.kind == "unexpected":
            connections.release(slot, "error")
            last_problem = page.detail
            log("WARN", f"{page.detail} ({where})")
            continue
        connections.release(slot, "ok")
        result = judge_results(company, page.results, settings)
        result.searches = searches
        log("OK", f"{len(page.results)} results ({where})")
        for candidate in result.candidates:
            log("INFO", f"#{candidate.rank} {candidate.verdict.upper():<7} {candidate.url} · {candidate.reason}")
        if result.status == FOUND:
            log("FOUND", f"{result.website} (result #{result.rank}: {result.match})")
        elif result.status == UNSURE:
            log("WARN", f"Unsure: {result.website} (result #{result.rank}: {result.match})")
        else:
            log("INFO", result.error)
        result.elapsed = time.monotonic() - started
        result.log = logs
        return result

    status = RATE_LIMITED if limited and last_problem != "Stopped" else FAILED
    log("ERROR", last_problem or "The search did not work")
    return FinderResult(company, status, error=last_problem or "The search did not work", searches=searches,
                        elapsed=time.monotonic() - started, log=logs)


def parse_companies(text: str) -> list[str]:
    """Company names, one per line, blank lines and repeats removed (letter case ignored)."""
    names: list[str] = []
    seen: set[str] = set()
    for line in (text or "").splitlines():
        name = " ".join(line.split()).strip("\"'")
        key = name.casefold()
        if name and key not in seen:
            seen.add(key)
            names.append(name)
    return names


# ----------------------------------------------------------------- the run
def find_websites(
    companies: list[str],
    connections: Connections,
    settings: FinderSettings,
    workers: int = 5,
    progress: Callable[[FinderResult, int], None] | None = None,
    cancelled: Callable[[], bool] | None = None,
) -> FinderSummary:
    summary = FinderSummary()

    def report(_index: int, result: FinderResult) -> None:
        summary.results.append(result)
        if progress:
            progress(result, len(companies))

    def give_up(_index: int, company: str, seconds: float) -> FinderResult:
        return FinderResult(company, FAILED, error=f"Gave up after {int(seconds)}s", elapsed=seconds)

    def on_error(_index: int, company: str, exc: Exception) -> FinderResult:
        return FinderResult(company, FAILED, error=f"Unexpected error: {exc}")

    # More workers than connections would only wait in line.
    workers = max(1, min(workers, connections.alive() or 1))
    summary.stopped = run_parallel(
        companies,
        lambda _index, company: find_website(company, connections, settings, cancelled),
        workers, report, cancelled, hard_limit=COMPANY_HARD_LIMIT, give_up=give_up, on_error=on_error,
    )
    return summary
