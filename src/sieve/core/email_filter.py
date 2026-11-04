"""Clean up raw email candidates and reject junk.

Scraped pages and documents are full of things that look like email addresses
but are not useful contacts: placeholders (``name@example.com``), automated
senders (``noreply@...``), disposable inboxes, error-tracking keys
(``a1b2c3...@o12345.ingest.sentry.io``) and image names (``logo@2x.png``).

``EmailRules`` holds the user-editable block lists; ``EmailFilter`` applies them
and explains every rejection.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from urllib.parse import unquote

# ------------------------------------------------------------------ defaults
DEFAULT_BLOCKED_DOMAINS = """
example.com
example.org
test.com
localhost
email.com
domain.com
mysite.com
yoursite.com
yourdomain.com
website.com
company.com
doe.com
sample.com
mailservice.com
alanadi.com
ornek.com
yourname.com
mailinator.com
yopmail.com
yopmail.fr
yopmail.net
guerrillamail.com
10minutemail.com
temp-mail.org
trashmail.com
sharklasers.com
maildrop.cc
dispostable.com
getairmail.com
throwawaymail.com
tempmail.net
mail.tm
mail.gw
cool.fr.nf
jetable.org
temporarily.de
spamgourmet.com
sentry.io
sentry.com
sentry-cdn.com
wixpress.com
wix.com
noreply.com
amazonaws.com
reply.github.com
github.com
github.io
cloudflare.com
herokuapp.com
googleusercontent.com
wordpress.com
shopify.com
mail.ru
"""

DEFAULT_DOMAIN_KEYWORDS = """
sentry
wixpress
hostmaster
postmaster
no-reply
noreply
donotreply
mailinator
trashmail
tempmail
disposable
hs03.kep
.gov
cdn
static
image
img
upload
assets
media
storage
bucket
theme
template
"""

DEFAULT_BLOCKED_USERNAMES = """
noreply
no-reply
donotreply
mailer-daemon
postmaster
hostmaster
webmaster
support-team
support-bot
automail
notification
notifications
alert
alerts
jira
gitlab
github
bounce
bounces
system
security
daemon
root
privacy
test
example
demo
sample
username
user
admin-user
domain
name
email
firstname
lastname
yourname
yourmail
adiniz
ornek
eposta
"""

DEFAULT_USERNAME_PREFIXES = """
test.
test-
demo.
demo-
noreply
no-reply
"""

DEFAULT_BLOCKED_EMAILS = """
johndoe@gmail.com
john.smith@gmail.com
jane.doe@gmail.com
hello@gmail.com
test@gmail.com
name@email.com
admin@example.com
user@example.com
info@example.com
test@test.com
user@domain.com
email@email.com
me@privacy.net
someone@somewhere.com
mymail@mailservice.com
"""

_FILE_EXTENSIONS_TEXT = """
png jpg jpeg gif svg bmp webp avif ico tif tiff js css scss less html htm json xml
woff woff2 ttf eot otf mp3 mp4 wav avi mov zip tar gz rar 7z exe bin dmg iso apk
sql db bak log pdf
"""
FILE_EXTENSIONS = frozenset(_FILE_EXTENSIONS_TEXT.split())

_VALID = re.compile(r"^[a-z0-9._%+\-]+@(?:[^\W_](?:[\w\-]{0,61}[^\W_])?\.)+[^\W\d_]{2,63}$")
_LEADING_PHONE = re.compile(r"^[\d\-]{6,}")
_WRAPPING = "<>;\"'()[]{},: \t\r\n."
_ESCAPE = re.compile(r"\\u([0-9a-fA-F]{4})|\\x([0-9a-fA-F]{2})")
_LEFTOVER_ESCAPE = re.compile(r"\\?u00(?:3[ceCE]|22|27|26|[aA]0)")
_PERCENT = re.compile(r"%[0-9a-fA-F]{2}")
_OBFUSCATED_AT = re.compile(r"\s*[\(\[\{]\s*at\s*[\)\]\}]\s*|\s+_at_\s+", re.IGNORECASE)
_OBFUSCATED_DOT = re.compile(r"\s*[\(\[\{]\s*dot\s*[\)\]\}]\s*", re.IGNORECASE)
_HEX = re.compile(r"^[a-f0-9]{10,}$")
_HEX_RUN = re.compile(r"[0-9a-f]{20,}")


def _lines(text: str) -> list[str]:
    seen: set[str] = set()
    items: list[str] = []
    for line in text.splitlines():
        item = line.strip().lower()
        if item and item not in seen:
            seen.add(item)
            items.append(item)
    return items


# --------------------------------------------------------------------- rules
@dataclass
class EmailRules:
    blocked_domains: list[str] = field(default_factory=lambda: _lines(DEFAULT_BLOCKED_DOMAINS))
    domain_keywords: list[str] = field(default_factory=lambda: _lines(DEFAULT_DOMAIN_KEYWORDS))
    blocked_usernames: list[str] = field(default_factory=lambda: _lines(DEFAULT_BLOCKED_USERNAMES))
    username_prefixes: list[str] = field(default_factory=lambda: _lines(DEFAULT_USERNAME_PREFIXES))
    blocked_emails: list[str] = field(default_factory=lambda: _lines(DEFAULT_BLOCKED_EMAILS))
    #: Reject usernames/domains that look like hashes or tokens.
    block_tokens: bool = True
    #: Reject placeholder domains such as example.net, test.org or yourdomain.co.
    block_placeholders: bool = True

    LIST_FIELDS = (
        "blocked_domains",
        "domain_keywords",
        "blocked_usernames",
        "username_prefixes",
        "blocked_emails",
    )

    def to_dict(self) -> dict:
        data: dict = {name: "\n".join(getattr(self, name)) for name in self.LIST_FIELDS}
        data["block_tokens"] = self.block_tokens
        data["block_placeholders"] = self.block_placeholders
        return data

    @classmethod
    def from_dict(cls, data: dict) -> EmailRules:
        rules = cls()
        for name in cls.LIST_FIELDS:
            value = data.get(name)
            if isinstance(value, str):
                setattr(rules, name, _lines(value))
        for name in ("block_tokens", "block_placeholders"):
            if isinstance(data.get(name), bool):
                setattr(rules, name, data[name])
        return rules


# ------------------------------------------------------------------ cleaning
def prepare_text(text: str) -> str:
    """Undo common encodings and obfuscations before looking for emails.

    Handles ``%40``-style URL encoding, ``\\u0040`` / ``\\x40`` escapes, stray
    JSON escape leftovers (``u003e``) and ``name (at) site (dot) com``.
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
    """Lower-case and tidy a candidate; None if it is not a plausible address."""
    if not raw:
        return None
    email = unicodedata.normalize("NFKC", raw).strip(_WRAPPING).lower()
    if email.startswith("mailto:"):
        email = email[7:]
    email = _LEADING_PHONE.sub("", email)  # "05555555555info@x.com" glued to a phone number
    if not 6 <= len(email) <= 100 or not _VALID.match(email):
        return None
    local = email.split("@", 1)[0]
    if local.startswith(".") or local.endswith(".") or ".." in local:
        return None
    return email


def _looks_like_token(part: str) -> bool:
    if _HEX.match(part) or _HEX_RUN.search(part):
        return True
    plain = re.sub(r"[._\-+]", "", part)
    # Long run of letters and digits with no separators, e.g. "a8f3k2m9x7q1w5e4".
    digits = sum(ch.isdigit() for ch in plain)
    return len(plain) == len(part) and len(part) >= 16 and digits >= 3


# -------------------------------------------------------------------- filter
@dataclass(frozen=True)
class Verdict:
    email: str
    #: None when the address is accepted, otherwise why it was rejected.
    reason: str | None = None

    @property
    def ok(self) -> bool:
        return self.reason is None


class EmailFilter:
    def __init__(self, rules: EmailRules | None = None) -> None:
        rules = rules or EmailRules()
        self.rules = rules
        self._domains = set(rules.blocked_domains)
        self._usernames = set(rules.blocked_usernames)
        self._emails = set(rules.blocked_emails)
        self._keywords = tuple(rules.domain_keywords)
        self._prefixes = tuple(rules.username_prefixes)

    def check(self, email: str) -> Verdict:
        """Judge an already normalized address."""
        local, _, domain = email.partition("@")
        labels = domain.split(".")
        tld = labels[-1]

        if tld in FILE_EXTENSIONS:
            return Verdict(email, "File name")
        if email in self._emails:
            return Verdict(email, "Blocked address")
        if domain in self._domains or any(domain.endswith("." + d) for d in self._domains):
            return Verdict(email, f"Blocked domain ({domain})")
        for keyword in self._keywords:
            if keyword in domain:
                return Verdict(email, f"Domain contains “{keyword}”")
        if local in self._usernames:
            return Verdict(email, f"Blocked username ({local})")
        for prefix in self._prefixes:
            if local.startswith(prefix):
                return Verdict(email, f"Username starts with “{prefix}”")
        if self.rules.block_placeholders and any(
            label in ("example", "test", "sample") or label.startswith(("example", "yourdomain", "yoursite"))
            for label in labels[:-1]
        ):
            return Verdict(email, "Placeholder domain")
        if self.rules.block_placeholders and "yourname" in local:
            return Verdict(email, "Placeholder username")
        if self.rules.block_tokens:
            if len(local) > 35 or _looks_like_token(local):
                return Verdict(email, "Looks like a token or hash")
            if any(_looks_like_token(label) for label in labels[:-1]):
                return Verdict(email, "Domain looks like a token or hash")
        return Verdict(email)

    def judge(self, raw: str) -> Verdict | None:
        """Normalize then check; None if ``raw`` is not an email at all."""
        email = normalize_email(raw)
        return None if email is None else self.check(email)
