"""Encrypted storage for secrets such as API keys and logins.

On Windows, values are encrypted with DPAPI (``CryptProtectData``), so they can
only be decrypted by the same Windows user on the same machine. Other
platforms are only used for development and store values base64-encoded.
"""

from __future__ import annotations

import base64
import json
import logging
import sys
from pathlib import Path

from sieve import paths

log = logging.getLogger(__name__)

#: Name of the GitHub token saved by versions before 0.14.2. Updates no longer need it;
#: it is only kept so a token left on the computer can be removed.
GITHUB_TOKEN = "github_token"

if sys.platform == "win32":
    import ctypes
    from ctypes import wintypes

    class _DataBlob(ctypes.Structure):
        _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]

    _crypt32 = ctypes.windll.crypt32
    _kernel32 = ctypes.windll.kernel32
    _kernel32.LocalFree.argtypes = [ctypes.c_void_p]
    _kernel32.LocalFree.restype = ctypes.c_void_p
    _CRYPTPROTECT_UI_FORBIDDEN = 0x01

    def _call(func, data: bytes) -> bytes:
        buffer = ctypes.create_string_buffer(data, len(data))
        blob_in = _DataBlob(len(data), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_char)))
        blob_out = _DataBlob()
        ok = func(
            ctypes.byref(blob_in), None, None, None, None,
            _CRYPTPROTECT_UI_FORBIDDEN, ctypes.byref(blob_out),
        )
        if not ok:
            raise ctypes.WinError()
        try:
            return ctypes.string_at(blob_out.pbData, blob_out.cbData)
        finally:
            _kernel32.LocalFree(ctypes.cast(blob_out.pbData, ctypes.c_void_p))

    def _protect(data: bytes) -> bytes:
        return _call(_crypt32.CryptProtectData, data)

    def _unprotect(data: bytes) -> bytes:
        return _call(_crypt32.CryptUnprotectData, data)

else:

    def _protect(data: bytes) -> bytes:
        return data

    def _unprotect(data: bytes) -> bytes:
        return data


class CredentialStore:
    def __init__(self, path: Path | None = None) -> None:
        self._path = path or paths.config_dir() / "credentials.json"

    def _read(self) -> dict[str, str]:
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return {}
        except (OSError, ValueError):
            log.exception("Credential file is unreadable")
            return {}
        return data if isinstance(data, dict) else {}

    def _write(self, data: dict[str, str]) -> None:
        tmp = self._path.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
        tmp.replace(self._path)

    def get(self, name: str) -> str | None:
        encoded = self._read().get(name)
        if not encoded:
            return None
        try:
            return _unprotect(base64.b64decode(encoded)).decode("utf-8")
        except Exception:
            log.exception("Could not decrypt credential %r", name)
            return None

    def set(self, name: str, value: str) -> None:
        data = self._read()
        data[name] = base64.b64encode(_protect(value.encode("utf-8"))).decode("ascii")
        self._write(data)

    def delete(self, name: str) -> None:
        data = self._read()
        if data.pop(name, None) is not None:
            self._write(data)
