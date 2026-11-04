import pytest

from sieve.core.email_filter import EmailFilter, EmailRules, normalize_email, prepare_text


@pytest.mark.parametrize(
    "email",
    [
        "info@acme.com.tr",
        "john.smith1985@gmail.com",
        "sales@contestshop.com",  # contains "test" but is not a placeholder
        "satis@örnek-firma.com.tr",
        "ceo@latestnews.io",
    ],
)
def test_real_addresses_pass(email):
    assert EmailFilter().check(email).ok


@pytest.mark.parametrize(
    ("email", "reason"),
    [
        ("logo@2x.png", "File name"),
        ("test@test.com", "Blocked address"),
        ("someone@mailinator.com", "Blocked domain"),
        ("a@o123.ingest.sentry.io", "Blocked domain"),
        ("x@452.wixpress.com", "Blocked domain"),
        ("info@city.gov.tr", "Domain contains"),
        ("hello@cdn.acme.com", "Domain contains"),
        ("noreply@acme.com", "Blocked username"),
        ("noreply-123@acme.com", "Username starts with"),
        ("test.user@acme.com", "Username starts with"),
        ("info@example.net", "Placeholder domain"),
        ("info@yourdomain.co", "Placeholder domain"),
        ("info.yourname@acme.com", "Placeholder username"),
        ("5e9d8f7a3b2c1d0e@acme.com", "Looks like a token"),
        ("a8f3k2m9x7q1w5e4z@acme.com", "Looks like a token"),
        ("x" * 36 + "@acme.com", "Looks like a token"),
    ],
)
def test_junk_is_rejected_with_reason(email, reason):
    verdict = EmailFilter().check(email)
    assert not verdict.ok
    assert verdict.reason.startswith(reason)


def test_rules_can_be_turned_off_and_edited():
    rules = EmailRules(block_tokens=False, block_placeholders=False)
    rules.blocked_domains = ["spam.com"]
    flt = EmailFilter(rules)
    assert flt.check("5e9d8f7a3b2c1d0e@acme.com").ok
    assert flt.check("info@example.net").ok
    assert not flt.check("a@spam.com").ok
    assert flt.check("a@yopmail.com").ok


def test_rules_round_trip_through_dict():
    rules = EmailRules()
    rules.blocked_domains = ["a.com", "b.com"]
    rules.block_tokens = False
    restored = EmailRules.from_dict(rules.to_dict())
    assert restored.blocked_domains == ["a.com", "b.com"]
    assert restored.block_tokens is False
    assert restored.blocked_usernames == EmailRules().blocked_usernames


def test_from_dict_ignores_bad_values():
    restored = EmailRules.from_dict({"blocked_domains": 5, "block_tokens": "yes"})
    assert restored == EmailRules()


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("<Info@Acme.COM>;", "info@acme.com"),
        ("mailto:Sales@acme.com", "sales@acme.com"),
        ("05555555555info@acme.com", "info@acme.com"),
        ("2020agency@acme.com", "2020agency@acme.com"),
        ("a..b@acme.com", None),
        ("not-an-email", None),
        ("a@b.c", None),
    ],
)
def test_normalize_email(raw, expected):
    assert normalize_email(raw) == expected


def test_prepare_text_undoes_encodings_and_obfuscation():
    text = r"mail: info%40acme.com, sales@acme.com, u003esupport@acme.com, ceo (at) acme [dot] com"
    prepared = prepare_text(text)
    for email in ("info@acme.com", "sales@acme.com", "support@acme.com", "ceo@acme.com"):
        assert email in prepared


def test_judge():
    flt = EmailFilter()
    assert flt.judge("garbage") is None
    assert flt.judge("Info@Acme.com").email == "info@acme.com"
