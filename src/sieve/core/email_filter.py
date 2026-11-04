"""Decide whether a string that looks like an email address is a real, useful contact.

Checks run in layers, cheapest and most certain first:

1. **Syntax**: a plausible local part, an ``@`` and a domain made of valid labels.
2. **Real domain ending**: the top-level domain must exist in the IANA list, which
   rejects things like ``logo@2x.png`` or ``bundle@4.2.min.js`` without any keyword.
3. **Your lists**: addresses, domains or usernames you always allow or always block.
4. **Categories** (each can be switched off):

   * ``reserved``: documentation domains reserved by RFC 2606/6761 (example.com, .test).
   * ``placeholder``: template addresses in English, Turkish and German.
   * ``automated``: no-reply, mailer-daemon, bounce and similar senders.
   * ``disposable``: temporary inbox services (community list, 10,000+ domains).
   * ``service``: sending, tracking and error-reporting infrastructure (Sentry, Wix, SES).
   * ``token``: random-looking strings such as hashes, UUIDs and generated IDs.

5. **Mail server (MX) check**, optional: the domain must exist and accept email.

Every rejection carries a short human-readable reason.
"""

from __future__ import annotations

import logging
import re
import threading
import unicodedata
from collections.abc import Callable
from dataclasses import dataclass, field
from functools import lru_cache
from urllib.parse import unquote

from sieve import paths

log = logging.getLogger(__name__)

# ----------------------------------------------------------------- categories
CATEGORIES: dict[str, tuple[str, str]] = {
    "reserved": (
        "Example domains",
        "Domains reserved for documentation: example.com/.net/.org and endings such as .test or .invalid.",
    ),
    "placeholder": (
        "Placeholder addresses",
        "Template addresses in English, Turkish and German, e.g. yourname@, max.mustermann@, "
        "adiniz@, info@yourdomain.com, info@siteniz.com.",
    ),
    "automated": (
        "Automated senders",
        "Addresses nobody reads: noreply, no-reply, mailer-daemon, bounce, yanitlamayin, keine-antwort.",
    ),
    "disposable": (
        "Disposable inboxes",
        "Temporary email services such as Mailinator or 10 Minute Mail (over 10,000 domains).",
    ),
    "service": (
        "Service domains",
        "Sending, tracking and error-reporting systems (Sentry, Wix internals, Amazon SES, Mailchimp, "
        "SendGrid, GitHub no-reply).",
    ),
    "token": (
        "Random-looking addresses",
        "Hashes, UUIDs and generated IDs, e.g. 5e9d8f7a3b2c1d0e@... or a8f3k2m9x7q1w5e4@...",
    ),
}

# --------------------------------------------------------------- built-in data
RESERVED_TLDS = frozenset({"test", "example", "invalid", "localhost", "local", "internal"})
RESERVED_DOMAINS = frozenset({"example.com", "example.net", "example.org", "example.edu"})

PLACEHOLDER_DOMAINS = frozenset({
    # English
    "domain.com", "yourdomain.com", "your-domain.com", "mydomain.com", "yoursite.com",
    "your-site.com", "mysite.com", "yourcompany.com", "your-company.com", "mycompany.com",
    "companyname.com", "yourwebsite.com", "mywebsite.com", "sitename.com", "domainname.com",
    "yourbusiness.com",
    # Turkish
    "siteniz.com", "sitenizinadi.com", "websiteniz.com", "alanadiniz.com", "alanadi.com",
    "firmaniz.com", "firmaadi.com", "firmaniz.com.tr", "sirketiniz.com", "sirketadi.com",
    "ornek.com", "ornek.com.tr", "ornekfirma.com", "domainadi.com", "sizinsiteniz.com",
    # German
    "beispiel.de", "beispiel.com", "beispiel.org", "musterfirma.de", "musterfirma.com",
    "mustermann.de", "mustermann.com", "ihre-domain.de", "ihredomain.de", "ihre-firma.de",
    "ihrefirma.de", "ihre-website.de", "meinedomain.de", "meine-domain.de",
})

PLACEHOLDER_USERNAMES = frozenset({
    # English
    "yourname", "your.name", "your-name", "your_name", "youremail", "your.email", "your-email",
    "yourmail", "firstname", "lastname", "firstname.lastname", "first.last", "name.surname",
    "john.doe", "jane.doe", "johndoe", "janedoe", "username", "user.name", "someone",
    "somebody", "name", "example", "sample",
    # Turkish
    "adiniz", "adinizsoyadiniz", "adiniz.soyadiniz", "ad.soyad", "adsoyad", "isim",
    "isim.soyisim", "isimsoyisim", "isminiz", "kullaniciadi", "epostaadresiniz",
    "eposta.adresiniz", "mailadresiniz", "ornek", "ornek.isim",
    # German
    "max.mustermann", "maxmustermann", "mustermann", "erika.mustermann", "vorname.nachname",
    "vorname", "nachname", "ihr.name", "ihrname", "ihre.email", "ihre-email", "beispiel",
})

AUTOMATED_USERNAMES = frozenset({
    "mailer-daemon", "mailerdaemon", "postmaster", "hostmaster", "bounce", "bounces",
    "bounced", "abuse", "notifications", "notification",
    "yanitlamayin", "yanitlamayiniz", "cevaplamayin", "cevaplamayiniz",
    "keine-antwort", "keineantwort", "nicht-antworten", "nichtantworten",
})
_AUTOMATED_PREFIX = re.compile(r"^(?:no[-_.]?reply|do[-_.]?not[-_.]?reply|dont[-_.]?reply)(?:$|[-_.+\d])")

SERVICE_DOMAINS = frozenset({
    "sentry.io", "sentry-cdn.com", "wixpress.com", "amazonses.com", "sendgrid.net",
    "mailgun.org", "mandrillapp.com", "mcsv.net", "mcdlv.net", "rsgsv.net", "list-manage.com",
    "sparkpostmail.com", "mktomail.com", "hubspotemail.net", "users.noreply.github.com",
    "noreply.github.com", "reply.github.com", "facebookmail.com", "bounces.google.com",
})

# Some file extensions are also real top-level domains (.zip, .mov); an address
# whose "domain" is a single short label plus one of these is almost always a file.
_FILE_LIKE_TLDS = frozenset({"zip", "mov"})

_SYNTAX = re.compile(
    r"^(?P<local>[a-z0-9!#$%&'*+/=?^_`{|}~\-]+(?:\.[a-z0-9!#$%&'*+/=?^_`{|}~\-]+)*)"
    r"@(?P<domain>(?:[^\W_](?:[\w\-]{0,61}[^\W_])?\.)+(?P<tld>[^\W\d_]{2,63}|xn--[a-z0-9\-]{1,59}))$"
)
_LEADING_PHONE = re.compile(r"^[\d\-]{6,}")
_WRAPPING = "<>;\"'()[]{},: \t\r\n."
_ESCAPE = re.compile(r"\\u([0-9a-fA-F]{4})|\\x([0-9a-fA-F]{2})")
_LEFTOVER_ESCAPE = re.compile(r"\\?u00(?:3[ceCE]|22|27|26|[aA]0)")
_PERCENT = re.compile(r"%[0-9a-fA-F]{2}")
_OBFUSCATED_AT = re.compile(r"\s*[\(\[\{]\s*(?:at|@)\s*[\)\]\}]\s*|\s+_at_\s+", re.IGNORECASE)
_OBFUSCATED_DOT = re.compile(r"\s*[\(\[\{]\s*(?:dot|punkt|nokta)\s*[\)\]\}]\s*", re.IGNORECASE)
_UUID = re.compile(r"^[0-9a-f]{8}-?[0-9a-f]{4}-?[0-9a-f]{4}-?[0-9a-f]{4}-?[0-9a-f]{12}$")
_HEX = re.compile(r"^[0-9a-f]{12,}$")
_RUNS = re.compile(r"[a-z]+|\d+")


# ------------------------------------------------------------------ data files
def _read_list(name: str) -> frozenset[str]:
    path = paths.resource_path("assets", "data", name)
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        log.warning("Reference list %s is missing; that check is skipped", name)
        return frozenset()
    return frozenset(line.strip().lower() for line in lines if line.strip() and not line.startswith("#"))


@lru_cache(maxsize=1)
def known_tlds() -> frozenset[str]:
    return _read_list("tlds.txt")


@lru_cache(maxsize=1)
def disposable_domains() -> frozenset[str]:
    return _read_list("disposable_domains.txt")


# ----------------------------------------------------------------- text prep
def prepare_text(text: str) -> str:
    """Undo common encodings and obfuscations before looking for addresses.

    Handles ``%40`` URL encoding, ``\\u0040`` / ``\\x40`` escapes, stray JSON escape
    leftovers (``u003e``) and ``name (at) site (dot) com`` in English, German
    ("punkt") and Turkish ("nokta").
    """
    if len(text) > 2_000_000:
        text = text[:2_000_000]
    text = unicodedata.normalize("NFKC", text)
    if "%" in text:
        text = _PERCENT.sub(lambda m: unquote(m.group(0)), text)
    if "\\" in text:

        def decode(match: re.Match[str]) -> str:
            try:
                return chr(int(match.group(1) or match.group(2), 16))
            except ValueError:
                return match.group(0)

        text = _ESCAPE.sub(decode, text)
    text = _LEFTOVER_ESCAPE.sub(" ", text)
    text = _OBFUSCATED_AT.sub("@", text)
    return _OBFUSCATED_DOT.sub(".", text)


def normalize_email(raw: str) -> str | None:
    """Lower-case and tidy a candidate; None if it is not a syntactically valid address."""
    if not raw:
        return None
    email = unicodedata.normalize("NFKC", raw).strip(_WRAPPING).lower()
    if email.startswith("mailto:"):
        email = email[7:]
    email = _LEADING_PHONE.sub("", email)  # "05555555555info@x.com" glued to a phone number
    if not 6 <= len(email) <= 254:
        return None
    match = _SYNTAX.match(email)
    if not match or len(match.group("local")) > 64:
        return None
    return email


def looks_random(part: str) -> bool:
    """True for hashes, UUIDs and generated IDs; False for names in any language.

    Length alone is not used, so long German or Turkish words
    (``datenschutzbeauftragter``, ``muhasebedepartmani``) are never flagged.
    """
    if _UUID.match(part):
        return True
    plain = re.sub(r"[._\-+]", "", part)
    if _HEX.match(plain) and any(ch.isdigit() for ch in plain) and any(ch.isalpha() for ch in plain):
        return True
    runs = _RUNS.findall(plain)
    digits = sum(len(run) for run in runs if run.isdigit())
    # Letters and digits switching back and forth: "a8f3k2m9x7".
    return len(plain) >= 10 and len(runs) >= 6 and digits >= 3


def _matches_domain(domain: str, domains: frozenset[str] | set[str]) -> str | None:
    """The entry of ``domains`` that ``domain`` equals or is a subdomain of."""
    labels = domain.split(".")
    for start in range(len(labels) - 1):
        candidate = ".".join(labels[start:])
        if candidate in domains:
            return candidate
    return None


# ------------------------------------------------------------------ settings
@dataclass
class FilterSettings:
    categories: dict[str, bool] = field(default_factory=lambda: dict.fromkeys(CATEGORIES, True))
    #: Entries are "name@site.com" (one address), "site.com" (a domain and its
    #: subdomains) or "name@" (a username at any domain).
    blocked: list[str] = field(default_factory=list)
    allowed: list[str] = field(default_factory=list)
    check_mx: bool = False

    def to_dict(self) -> dict:
        return {
            "categories": dict(self.categories),
            "blocked": "\n".join(self.blocked),
            "allowed": "\n".join(self.allowed),
            "check_mx": self.check_mx,
        }

    @classmethod
    def from_dict(cls, data: dict) -> FilterSettings:
        settings = cls()
        categories = data.get("categories")
        if isinstance(categories, dict):
            for key in CATEGORIES:
                if isinstance(categories.get(key), bool):
                    settings.categories[key] = categories[key]
        for name in ("blocked", "allowed"):
            value = data.get(name)
            if isinstance(value, str):
                setattr(settings, name, parse_entries(value))
        if isinstance(data.get("check_mx"), bool):
            settings.check_mx = data["check_mx"]
        return settings


def parse_entries(text: str) -> list[str]:
    seen: set[str] = set()
    entries: list[str] = []
    for line in text.splitlines():
        entry = line.strip().lower().removeprefix("mailto:")
        if entry and not entry.startswith("#") and entry not in seen:
            seen.add(entry)
            entries.append(entry)
    return entries


class _EntryList:
    """Matches addresses against "a@b.com", "b.com" and "a@" entries."""

    def __init__(self, entries: list[str]) -> None:
        self.addresses = {e for e in entries if "@" in e and not e.endswith("@") and not e.startswith("@")}
        self.usernames = {e[:-1] for e in entries if e.endswith("@")}
        self.domains = {e.lstrip("@") for e in entries if "@" not in e or e.startswith("@")}

    def match(self, email: str, local: str, domain: str) -> str | None:
        if email in self.addresses:
            return email
        if local in self.usernames:
            return local + "@"
        return _matches_domain(domain, self.domains) if self.domains else None


# -------------------------------------------------------------------- verdict
@dataclass(frozen=True)
class Verdict:
    email: str
    #: None when accepted; otherwise why it was rejected.
    reason: str | None = None
    #: The category key that rejected it ("syntax", "user", one of CATEGORIES, "mx").
    category: str | None = None

    @property
    def ok(self) -> bool:
        return self.reason is None


# ---------------------------------------------------------------- MX checks
NO_DOMAIN, NO_MAIL, ACCEPTS_MAIL, UNKNOWN = "no_domain", "no_mail", "ok", "unknown"


class DomainChecker:
    """Answers "can this domain receive email?" with DNS, caching every answer.

    ``lookup`` is injectable for tests; by default dnspython is used.
    """

    def __init__(self, lookup: Callable[[str], str] | None = None, timeout: float = 4.0) -> None:
        self._lookup = lookup or _DnsLookup(timeout)
        self._cache: dict[str, str] = {}
        self._lock = threading.Lock()

    def check(self, domain: str) -> str:
        with self._lock:
            cached = self._cache.get(domain)
        if cached is not None:
            return cached
        try:
            answer = self._lookup(domain)
        except Exception:
            log.debug("MX lookup failed for %s", domain, exc_info=True)
            answer = UNKNOWN
        with self._lock:
            self._cache[domain] = answer
        return answer


class _DnsLookup:
    def __init__(self, timeout: float) -> None:
        import dns.resolver

        self._dns = dns
        self._resolver = dns.resolver.Resolver()
        self._resolver.lifetime = timeout

    def __call__(self, domain: str) -> str:
        dns = self._dns
        name = domain.encode("idna").decode("ascii")
        try:
            answer = self._resolver.resolve(name, "MX")
            exchanges = [str(record.exchange).rstrip(".") for record in answer]
            # RFC 7505 "null MX": the domain explicitly accepts no email.
            return NO_MAIL if exchanges == [""] else ACCEPTS_MAIL
        except dns.resolver.NXDOMAIN:
            return NO_DOMAIN
        except dns.resolver.NoAnswer:
            pass
        except (dns.resolver.NoNameservers, dns.exception.Timeout):
            return UNKNOWN
        # No MX record: mail is delivered to the domain's own address if it has one.
        for record_type in ("A", "AAAA"):
            try:
                self._resolver.resolve(name, record_type)
                return ACCEPTS_MAIL
            except dns.resolver.NoAnswer:
                continue
            except dns.resolver.NXDOMAIN:
                return NO_DOMAIN
            except (dns.resolver.NoNameservers, dns.exception.Timeout):
                return UNKNOWN
        return NO_MAIL


# --------------------------------------------------------------------- filter
class EmailFilter:
    def __init__(
        self, settings: FilterSettings | None = None, domain_checker: DomainChecker | None = None
    ) -> None:
        self.settings = settings or FilterSettings()
        self._on = {key for key, enabled in self.settings.categories.items() if enabled}
        self._blocked = _EntryList(self.settings.blocked)
        self._allowed = _EntryList(self.settings.allowed)
        if self.settings.check_mx and domain_checker is None:
            domain_checker = DomainChecker()
        self._checker = domain_checker if self.settings.check_mx else None
        self._tlds = known_tlds()

    def check(self, email: str) -> Verdict:
        """Judge an address that already passed ``normalize_email``."""
        local, _, domain = email.partition("@")
        labels = domain.split(".")
        tld = labels[-1]

        if "reserved" in self._on and tld in RESERVED_TLDS:
            return Verdict(email, f"Reserved ending (.{tld})", "reserved")
        if self._tlds and tld not in self._tlds:
            return Verdict(email, f"Not a real domain ending (.{tld})", "syntax")
        if tld in _FILE_LIKE_TLDS and len(labels) == 2 and len(labels[0]) <= 12 and not labels[0].isalpha():
            return Verdict(email, f"Looks like a file name (.{tld})", "syntax")

        if self._allowed.match(email, local, domain):
            return Verdict(email)
        blocked = self._blocked.match(email, local, domain)
        if blocked:
            return Verdict(email, f"In your block list ({blocked})", "user")

        verdict = self._categories(email, local, domain, labels)
        if verdict is not None:
            return verdict

        if self._checker is not None:
            answer = self._checker.check(domain)
            if answer == NO_DOMAIN:
                return Verdict(email, "Domain does not exist", "mx")
            if answer == NO_MAIL:
                return Verdict(email, "Domain does not accept email", "mx")
        return Verdict(email)

    def _categories(self, email: str, local: str, domain: str, labels: list[str]) -> Verdict | None:
        on = self._on
        if "reserved" in on:
            if labels[-1] in RESERVED_TLDS:
                return Verdict(email, f"Reserved ending (.{labels[-1]})", "reserved")
            hit = _matches_domain(domain, RESERVED_DOMAINS)
            if hit:
                return Verdict(email, f"Example domain ({hit})", "reserved")
        if "placeholder" in on:
            hit = _matches_domain(domain, PLACEHOLDER_DOMAINS)
            if hit:
                return Verdict(email, f"Placeholder domain ({hit})", "placeholder")
            if local in PLACEHOLDER_USERNAMES:
                return Verdict(email, f"Placeholder username ({local})", "placeholder")
        if "automated" in on and (local in AUTOMATED_USERNAMES or _AUTOMATED_PREFIX.match(local)):
            return Verdict(email, f"Automated sender ({local})", "automated")
        if "service" in on:
            hit = _matches_domain(domain, SERVICE_DOMAINS)
            if hit:
                return Verdict(email, f"Service domain ({hit})", "service")
        if "disposable" in on:
            hit = _matches_domain(domain, disposable_domains())
            if hit:
                return Verdict(email, f"Disposable inbox ({hit})", "disposable")
        if "token" in on:
            if looks_random(local):
                return Verdict(email, "Random-looking username", "token")
            if any(looks_random(label) for label in labels[:-1] if not label.startswith("xn--")):
                return Verdict(email, "Random-looking domain", "token")
        return None

    def judge(self, raw: str) -> Verdict | None:
        """Normalize then check; None if ``raw`` is not an email address at all."""
        email = normalize_email(raw)
        return None if email is None else self.check(email)
