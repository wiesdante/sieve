import pytest

from sieve.core.link_extractor import (
    EMAILS,
    TEXT,
    ExtractOptions,
    domain_of,
    emails_from_mailto,
    extract_from_text,
    find_emails,
    find_urls,
    normalize,
    url_key,
)


def test_finds_scheme_www_and_bare_domains():
    text = "Visit https://acme.example/shop?id=5, www.foo.com and bar.io today."
    assert find_urls(text) == [
        "https://acme.example/shop?id=5",
        "https://www.foo.com",
        "https://bar.io",
    ]


def test_bare_domains_can_be_turned_off():
    assert find_urls("see bar.io or www.foo.com", include_bare_domains=False) == [
        "https://www.foo.com"
    ]


@pytest.mark.parametrize(
    "text",
    [
        "report.pdf",
        "Node.js and main.py",
        "End of sentence.Next sentence",
        "version 1.2.3",
        "e.g. this",
        "U.S. policy",
    ],
)
def test_bare_domain_false_positives_are_ignored(text):
    assert find_urls(text) == []


def test_emails_are_not_links():
    assert find_urls("Mail john.doe@example.com or visit example.com") == ["https://example.com"]


def test_trailing_punctuation_and_brackets():
    text = "(see https://en.wikipedia.org/wiki/Python_(language)). Also https://x.com/a/."
    assert find_urls(text) == [
        "https://en.wikipedia.org/wiki/Python_(language)",
        "https://x.com/a",
    ]


def test_glued_urls_are_split():
    assert find_urls("https://a.com/xhttps://b.com/y") == ["https://a.com/x", "https://b.com/y"]


def test_unicode_domain():
    assert find_urls("https://örnek.com.tr/ürün") == ["https://örnek.com.tr/ürün"]


def test_normalize_and_keys():
    assert normalize("www.Example.com/path/).") == "https://www.Example.com/path"
    assert url_key("http://www.Example.com/") == url_key("https://example.com")
    assert url_key("https://example.com/a") != url_key("https://example.com/b")
    assert domain_of("https://WWW.Shop.Example.com/x") == "shop.example.com"


def test_text_extraction_dedupes_and_keeps_order():
    result = extract_from_text("b.com a.com http://www.B.com/ https://a.com/page")
    assert result.lines == ["https://b.com", "https://a.com", "https://a.com/page"]
    assert result.total_found == 4
    assert all(link.kind == TEXT and link.page is None for link in result.links)


def test_domains_only():
    result = extract_from_text(
        "https://a.com/x https://www.a.com/y https://shop.b.com/z",
        ExtractOptions(domains_only=True),
    )
    assert result.lines == ["a.com", "shop.b.com"]


# ---------------------------------------------------------------- emails
def test_find_emails():
    text = "Write to John.Doe+sales@Example.co.uk, support@örnek.com.tr or (info@acme.io)."
    assert find_emails(text) == [
        "John.Doe+sales@Example.co.uk",
        "support@örnek.com.tr",
        "info@acme.io",
    ]


@pytest.mark.parametrize("text", ["logo@2x.png", "user@localhost", "@handle", "a..b@x.com", "a@b"])
def test_email_false_positives(text):
    assert find_emails(text) == []


def test_mailto_links():
    assert emails_from_mailto("mailto:a@x.com,b%40y.org?subject=Hi") == ["a@x.com", "b@y.org"]
    assert emails_from_mailto("https://x.com") == []


def test_email_mode_dedupes_ignoring_case_and_keeps_first_form():
    result = extract_from_text(
        "Sales@Acme.io and sales@acme.io, see https://acme.io", ExtractOptions(mode=EMAILS)
    )
    assert result.lines == ["Sales@Acme.io"]
    assert result.total_found == 2


def test_email_domains_only():
    result = extract_from_text("a@x.com b@X.com c@y.org", ExtractOptions(mode=EMAILS, domains_only=True))
    assert result.lines == ["x.com", "y.org"]


def test_invalid_mode():
    with pytest.raises(ValueError):
        ExtractOptions(mode="phones")
