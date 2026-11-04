import pytest

from sieve.core.email_filter import (
    ACCEPTS_MAIL,
    CATEGORIES,
    NO_DOMAIN,
    NO_MAIL,
    UNKNOWN,
    DomainChecker,
    EmailFilter,
    FilterSettings,
    known_tlds,
    looks_random,
    normalize_email,
    prepare_text,
)

# Real-looking contacts in English, Turkish and German that must never be rejected.
REAL = [
    "info@acme.com.tr",
    "john.smith1985@gmail.com",
    "sales@contestshop.com",
    "ceo@latestnews.io",
    "satis@örnek-firma.com.tr",
    "muhasebe@firma.com.tr",
    "insankaynaklari@holding.com.tr",
    "mail@schreinerei-mueller.de",
    "datenschutzbeauftragter@stadtwerke-beispielstadt.de",
    "geschaeftsfuehrung@mueller-gmbh.de",
    "kontakt@müller.de",
    "privacy@company.co.uk",
    "webmaster@smallshop.at",
    "security@bank.ch",
    "info@mediamarkt.com.tr",
    "hello@socialmediaajans.com",
    "info@city.gov.tr",
    "user123abc456@hotmail.com",
    "a.b@x.museum",
    "satis@xn--rnek-1oa.com",
]


@pytest.mark.parametrize("email", REAL)
def test_real_addresses_pass(email):
    verdict = EmailFilter().judge(email)
    assert verdict is not None and verdict.ok, verdict


@pytest.mark.parametrize(
    ("email", "category", "reason"),
    [
        ("logo@2x.png", "syntax", "Not a real domain ending"),
        ("bundle@4.2.min.js", "syntax", "Not a real domain ending"),
        ("icon@3x.webp", "syntax", "Not a real domain ending"),
        ("img@2x.zip", "syntax", "Looks like a file name"),
        ("info@example.com", "reserved", "Example domain"),
        ("info@mail.example.org", "reserved", "Example domain"),
        ("a@shop.test", "reserved", "Reserved ending"),
        ("yourname@gmail.com", "placeholder", "Placeholder username"),
        ("max.mustermann@web.de", "placeholder", "Placeholder username"),
        ("adiniz@firma.com.tr", "placeholder", "Placeholder username"),
        ("info@yourdomain.com", "placeholder", "Placeholder domain"),
        ("info@siteniz.com", "placeholder", "Placeholder domain"),
        ("kontakt@musterfirma.de", "placeholder", "Placeholder domain"),
        ("noreply@shop.com", "automated", "Automated sender"),
        ("no-reply-42@shop.com", "automated", "Automated sender"),
        ("do_not_reply@shop.com", "automated", "Automated sender"),
        ("mailer-daemon@shop.com", "automated", "Automated sender"),
        ("yanitlamayin@banka.com.tr", "automated", "Automated sender"),
        ("keine-antwort@versand.de", "automated", "Automated sender"),
        ("sales@mailinator.com", "disposable", "Disposable inbox"),
        ("x@yopmail.com", "disposable", "Disposable inbox"),
        ("abc@o450123.ingest.sentry.io", "service", "Service domain"),
        ("605a7baede84@sentry.wixpress.com", "service", "Service domain"),
        ("abc@eu-west-1.amazonses.com", "service", "Service domain"),
        ("5e9d8f7a3b2c1d0e@shop.com", "token", "Random-looking username"),
        ("a8f3k2m9x7q1w5e4z@shop.com", "token", "Random-looking username"),
        ("3f2504e0-4f89-11d3-9a0c-0305e82c3301@shop.com", "token", "Random-looking username"),
    ],
)
def test_junk_is_rejected_with_category_and_reason(email, category, reason):
    verdict = EmailFilter().judge(email)
    assert verdict is not None and not verdict.ok
    assert verdict.category == category
    assert verdict.reason.startswith(reason)


@pytest.mark.parametrize(
    "word",
    ["datenschutzbeauftragter", "muhasebedepartmani", "kundenservice", "john.smith1985", "info2024",
     "user123abc456"],
)
def test_names_are_not_random(word):
    assert not looks_random(word)


def test_categories_can_be_switched_off():
    settings = FilterSettings()
    settings.categories["automated"] = False
    assert EmailFilter(settings).judge("noreply@shop.com").ok
    assert not EmailFilter(settings).judge("info@example.com").ok


def test_file_names_are_rejected_even_with_every_category_off():
    settings = FilterSettings(categories=dict.fromkeys(CATEGORIES, False))
    assert not EmailFilter(settings).judge("logo@2x.png").ok


def test_user_block_and_allow_lists():
    settings = FilterSettings(
        blocked=["spam@shop.com", "agency.com", "test@"],
        allowed=["noreply@important.com", "mailinator.com"],
    )
    flt = EmailFilter(settings)
    assert flt.judge("spam@shop.com").category == "user"
    assert flt.judge("info@sub.agency.com").reason == "In your block list (agency.com)"
    assert flt.judge("test@anything.com").category == "user"
    assert flt.judge("noreply@important.com").ok
    assert flt.judge("x@mailinator.com").ok
    assert not flt.judge("logo@2x.png").ok  # allow list never overrides a non-address


def test_settings_round_trip_and_bad_values():
    settings = FilterSettings(blocked=["a.com"], allowed=["b@"], check_mx=True)
    settings.categories["token"] = False
    restored = FilterSettings.from_dict(settings.to_dict())
    assert restored == settings
    assert FilterSettings.from_dict({"categories": "x", "blocked": 3, "check_mx": "yes"}) == FilterSettings()


def test_mx_check_uses_the_answer_and_caches_it():
    answers = {"good.com": ACCEPTS_MAIL, "gone.com": NO_DOMAIN, "nomail.com": NO_MAIL, "flaky.com": UNKNOWN}
    calls = []

    def lookup(domain):
        calls.append(domain)
        return answers[domain]

    flt = EmailFilter(FilterSettings(check_mx=True), DomainChecker(lookup))
    assert flt.judge("a@good.com").ok
    assert flt.judge("a@gone.com").reason == "Domain does not exist"
    assert flt.judge("a@nomail.com").reason == "Domain does not accept email"
    assert flt.judge("a@flaky.com").ok  # unknown never rejects
    assert flt.judge("b@good.com").ok
    assert calls.count("good.com") == 1


def test_mx_lookup_errors_count_as_unknown():
    def broken(domain):
        raise RuntimeError("network down")

    assert DomainChecker(broken).check("x.com") == UNKNOWN


def test_mx_is_not_queried_for_addresses_already_rejected():
    calls = []
    flt = EmailFilter(FilterSettings(check_mx=True), DomainChecker(lambda d: calls.append(d) or ACCEPTS_MAIL))
    flt.judge("noreply@shop.com")
    assert calls == []


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("<Info@Acme.COM>;", "info@acme.com"),
        ("mailto:Sales@acme.com", "sales@acme.com"),
        ("05555555555info@acme.com", "info@acme.com"),
        ("2020agency@acme.com", "2020agency@acme.com"),
        ("a..b@acme.com", None),
        (".a@acme.com", "a@acme.com"),
        ("not-an-email", None),
        ("a@b.c", None),
        ("x" * 65 + "@acme.com", None),
    ],
)
def test_normalize_email(raw, expected):
    assert normalize_email(raw) == expected


def test_prepare_text_handles_encodings_and_three_languages():
    text = (
        r"info%40acme.com, sales@acme.com, u003esupport@acme.com, "
        "ceo (at) acme [dot] com, buero [at] firma (punkt) de, satis (at) firma (nokta) com"
    )
    prepared = prepare_text(text)
    for email in ("info@acme.com", "sales@acme.com", "support@acme.com", "ceo@acme.com",
                  "buero@firma.de", "satis@firma.com"):
        assert email in prepared


def test_reference_lists_are_bundled():
    assert {"com", "tr", "de", "zip", "рф"} <= known_tlds()
    assert "png" not in known_tlds()
