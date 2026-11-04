"""Real DNS lookups; run in CI only (set SIEVE_NETWORK_TESTS=1)."""

import os

import pytest

from sieve.core.email_filter import ACCEPTS_MAIL, NO_DOMAIN, DomainChecker

pytestmark = pytest.mark.skipif(
    not os.environ.get("SIEVE_NETWORK_TESTS"), reason="network tests are disabled"
)
pytest.importorskip("dns.resolver")


def test_real_domain_accepts_mail():
    assert DomainChecker().check("gmail.com") == ACCEPTS_MAIL


def test_missing_domain_is_detected():
    assert DomainChecker().check("no-such-domain-sieve-check-7f3a9.com") == NO_DOMAIN


def test_unicode_domain_is_encoded():
    assert DomainChecker().check("müller.de") in (ACCEPTS_MAIL, "no_mail")
