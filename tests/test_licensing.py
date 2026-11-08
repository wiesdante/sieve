from datetime import date

import pytest

pytest.importorskip("cryptography")

from sieve.core import licensing  # noqa: E402
from sieve.core.licensing import (  # noqa: E402
    LicenseError,
    issue_code,
    machine_code,
    owner_key,
    public_key_text,
    read_code,
    signing_key,
)

PASS = "correct horse battery staple"
MACHINE = machine_code("1b2f6c0e-1111-4c3a-9d55-000000000001")
OTHER = machine_code("1b2f6c0e-2222-4c3a-9d55-000000000002")


@pytest.fixture(scope="module")
def key():
    return signing_key(PASS)


@pytest.fixture(scope="module")
def public(key):
    return public_key_text(key)


def test_same_passphrase_gives_the_same_key(key, public):
    assert public_key_text(signing_key(PASS)) == public


def test_short_passphrase_is_refused():
    with pytest.raises(LicenseError, match="at least"):
        signing_key("too short")


def test_wrong_passphrase_is_refused(public):
    with pytest.raises(LicenseError, match="Wrong passphrase"):
        owner_key("another long passphrase", public)


def test_machine_code_shape_and_stability():
    assert len(MACHINE) == 19 and MACHINE.count("-") == 3
    assert machine_code("1B2F6C0E-1111-4C3A-9D55-000000000001") == MACHINE
    assert MACHINE != OTHER


def test_code_works_on_its_machine(key, public):
    code = issue_code(key, MACHINE, None, today=date(2026, 11, 8))
    result = read_code(code, public, MACHINE, today=date(2030, 1, 1))
    assert result.expires is None and result.issued == date(2026, 11, 8)


def test_code_accepts_spaces_and_lower_case(key, public):
    code = issue_code(key, MACHINE.lower().replace("-", " "), 30, today=date(2026, 11, 8))
    assert read_code(" " + code.lower().replace("-", "  ") + "\n", public, MACHINE, today=date(2026, 11, 9))


def test_code_does_not_work_on_another_machine(key, public):
    code = issue_code(key, MACHINE, None)
    with pytest.raises(LicenseError, match="another computer"):
        read_code(code, public, OTHER)


def test_code_expires(key, public):
    code = issue_code(key, MACHINE, 30, today=date(2026, 11, 8))
    assert read_code(code, public, MACHINE, today=date(2026, 12, 8)).days_left(date(2026, 12, 8)) == 0
    with pytest.raises(LicenseError, match="expired"):
        read_code(code, public, MACHINE, today=date(2026, 12, 9))


def test_edited_or_foreign_codes_are_rejected(key, public):
    code = issue_code(key, MACHINE, None)
    tampered = code[:10] + ("A" if code[10] != "A" else "B") + code[11:]
    with pytest.raises(LicenseError):
        read_code(tampered, public, MACHINE)
    stranger = signing_key("someone else's long passphrase")
    with pytest.raises(LicenseError, match="not genuine"):
        read_code(issue_code(stranger, MACHINE, None), public, MACHINE)
    with pytest.raises(LicenseError):
        read_code("hello", public, MACHINE)


def test_bad_machine_code_input(key):
    with pytest.raises(LicenseError, match="16 letters"):
        issue_code(key, "1234", None)


def test_durations_offered():
    assert dict(licensing.DURATIONS)["Unlimited"] is None
