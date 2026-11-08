"""Activation codes that only the owner can issue.

The owner's passphrase is stretched with scrypt into an Ed25519 signing key; the
matching public key is built into the app (:data:`sieve.licensing_key.PUBLIC_KEY`).
An activation code is a small record (the machine it is for, when it was issued,
when it expires) signed with that key. The app checks the signature with the
public key, so a code cannot be made without the passphrase, and nothing secret is
stored anywhere: the passphrase is typed when a code is needed and forgotten again.

A code is tied to one computer through a short machine code derived from Windows'
machine GUID, so a code given to one person does not work on another computer.

This keeps ordinary users from using the app without permission. It is not meant to
stop someone who edits the open source code.
"""

from __future__ import annotations

import base64
import hashlib
import secrets
import struct
import sys
import uuid
from dataclasses import dataclass
from datetime import date, timedelta

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

FORMAT_VERSION = 1
#: Fixed salt: the passphrase alone decides the key, so it can be typed on any computer.
_SALT = b"sieve-owner-key/v1/wiesdante"
#: scrypt cost (about 128 MiB and a fraction of a second): slows down passphrase guessing.
_SCRYPT = {"n": 2**17, "r": 8, "p": 1, "maxmem": 256 * 1024 * 1024}
MIN_PASSPHRASE = 12
_EPOCH = date(2026, 1, 1)
_PAYLOAD = struct.Struct(">B10sHH3s")  # version, machine, issued day, expiry day (0 = never), serial
_SIGNATURE = 64
#: Durations offered when issuing a code (label, days; None = no end date).
DURATIONS = (("Unlimited", None), ("7 days", 7), ("30 days", 30), ("90 days", 90), ("1 year", 365))


class LicenseError(ValueError):
    pass


# ------------------------------------------------------------------ keys
def signing_key(passphrase: str) -> Ed25519PrivateKey:
    """The owner's signing key, derived from the passphrase."""
    if len(passphrase) < MIN_PASSPHRASE:
        raise LicenseError(f"The passphrase must be at least {MIN_PASSPHRASE} characters long.")
    seed = hashlib.scrypt(passphrase.encode("utf-8"), salt=_SALT, dklen=32, **_SCRYPT)
    return Ed25519PrivateKey.from_private_bytes(seed)


def public_key_text(key: Ed25519PrivateKey) -> str:
    raw = key.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
    return base64.b64encode(raw).decode("ascii")


def owner_key(passphrase: str, public_key: str) -> Ed25519PrivateKey:
    """The signing key, only if the passphrase matches the app's built-in public key."""
    key = signing_key(passphrase)
    if not public_key or public_key_text(key) != public_key:
        raise LicenseError("Wrong passphrase.")
    return key


# --------------------------------------------------------------- machines
def _machine_guid() -> str:
    if sys.platform == "win32":
        try:
            import winreg

            with winreg.OpenKey(
                winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Cryptography",
                0, winreg.KEY_READ | winreg.KEY_WOW64_64KEY,
            ) as key:
                return str(winreg.QueryValueEx(key, "MachineGuid")[0])
        except OSError:
            pass
    return f"node-{uuid.getnode():012x}"


def _machine_bytes(guid: str | None = None) -> bytes:
    return hashlib.sha256(f"sieve-machine:{(guid or _machine_guid()).lower()}".encode()).digest()[:10]


def format_machine_code(raw: bytes) -> str:
    text = base64.b32encode(raw).decode("ascii")  # 10 bytes -> 16 letters, no padding
    return "-".join(text[i:i + 4] for i in range(0, 16, 4))


def machine_code(guid: str | None = None) -> str:
    """This computer's code, e.g. ``7K3F-9QX2-MW4D-QZ8A``; changes when Windows is reinstalled."""
    return format_machine_code(_machine_bytes(guid))


def parse_machine_code(text: str) -> bytes:
    cleaned = "".join(ch for ch in text.upper() if ch.isalnum())
    if len(cleaned) != 16:
        raise LicenseError("A machine code has 16 letters and digits, like 7K3F-9QX2-MW4D-QZ8A.")
    try:
        return base64.b32decode(cleaned)
    except ValueError as exc:
        raise LicenseError("That is not a valid machine code.") from exc


# ------------------------------------------------------------------ codes
def _day(value: date) -> int:
    return max(0, (value - _EPOCH).days)


def issue_code(key: Ed25519PrivateKey, machine: str, days: int | None, today: date | None = None) -> str:
    """An activation code for ``machine`` that ends after ``days`` (None: never)."""
    today = today or date.today()
    expiry = 0 if days is None else _day(today + timedelta(days=days))
    payload = _PAYLOAD.pack(FORMAT_VERSION, parse_machine_code(machine), _day(today), expiry,
                            secrets.token_bytes(3))
    text = base64.b32encode(payload + key.sign(payload)).decode("ascii").rstrip("=")
    return "-".join(text[i:i + 6] for i in range(0, len(text), 6))


@dataclass(frozen=True)
class License:
    machine: str
    issued: date
    expires: date | None

    def days_left(self, today: date | None = None) -> int | None:
        return None if self.expires is None else (self.expires - (today or date.today())).days


def read_code(code: str, public_key: str, machine: str | None = None, today: date | None = None) -> License:
    """Check an activation code for this computer; raises LicenseError with the reason."""
    cleaned = "".join(ch for ch in code.upper() if ch.isalnum())
    if not cleaned:
        raise LicenseError("Enter an activation code.")
    try:
        blob = base64.b32decode(cleaned + "=" * (-len(cleaned) % 8))
    except ValueError as exc:
        raise LicenseError("That is not a valid activation code.") from exc
    if len(blob) != _PAYLOAD.size + _SIGNATURE:
        raise LicenseError("That is not a valid activation code.")
    payload, signature = blob[:_PAYLOAD.size], blob[_PAYLOAD.size:]
    try:
        Ed25519PublicKey.from_public_bytes(base64.b64decode(public_key)).verify(signature, payload)
    except (InvalidSignature, ValueError) as exc:
        raise LicenseError("That activation code is not genuine.") from exc
    version, machine_raw, issued, expiry, _serial = _PAYLOAD.unpack(payload)
    if version != FORMAT_VERSION:
        raise LicenseError("That activation code is for another version of Sieve.")
    for_machine = format_machine_code(machine_raw)
    if for_machine != (machine or machine_code()):
        raise LicenseError("That activation code is for another computer.")
    result = License(for_machine, _EPOCH + timedelta(days=issued),
                     None if expiry == 0 else _EPOCH + timedelta(days=expiry))
    if result.expires is not None and (today or date.today()) > result.expires:
        raise LicenseError(f"That activation code expired on {result.expires:%d %b %Y}.")
    return result
