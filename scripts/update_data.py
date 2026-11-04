"""Download the reference lists bundled with Sieve into ``assets/data``.

* ``tlds.txt``: every top-level domain from IANA (Unicode form, one per line).
  https://data.iana.org/TLD/tlds-alpha-by-domain.txt
* ``disposable_domains.txt``: disposable / temporary email providers from the
  community-maintained list (CC0).
  https://github.com/disposable-email-domains/disposable-email-domains

Run by the "Update data" workflow every month; can also be run by hand.
"""

from __future__ import annotations

import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "assets" / "data"

TLD_URL = "https://data.iana.org/TLD/tlds-alpha-by-domain.txt"
DISPOSABLE_URL = (
    "https://raw.githubusercontent.com/disposable-email-domains/"
    "disposable-email-domains/main/disposable_email_blocklist.conf"
)


def _download(url: str) -> list[str]:
    request = urllib.request.Request(url, headers={"User-Agent": "sieve-data-updater"})
    with urllib.request.urlopen(request, timeout=30) as response:
        text = response.read().decode("utf-8")
    return [line.strip() for line in text.splitlines()]


def _to_unicode(label: str) -> str:
    if label.startswith("xn--"):
        try:
            return label.encode("ascii").decode("idna")
        except UnicodeError:
            return label
    return label


def tlds() -> list[str]:
    lines = [line.lower() for line in _download(TLD_URL) if line and not line.startswith("#")]
    result = sorted({_to_unicode(line) for line in lines} | set(lines))
    if len(result) < 1000:
        raise SystemExit(f"TLD list looks wrong ({len(result)} entries)")
    return result


def disposable_domains() -> list[str]:
    lines = [line.lower() for line in _download(DISPOSABLE_URL) if line and not line.startswith("#")]
    result = sorted(set(lines))
    if len(result) < 1000:
        raise SystemExit(f"Disposable domain list looks wrong ({len(result)} entries)")
    return result


def write(name: str, header: str, items: list[str]) -> None:
    DATA.mkdir(parents=True, exist_ok=True)
    path = DATA / name
    path.write_text(header + "\n".join(items) + "\n", encoding="utf-8")
    print(f"{path.relative_to(ROOT)}: {len(items)} entries")


def main() -> int:
    write("tlds.txt", f"# Top-level domains from {TLD_URL}\n", tlds())
    write(
        "disposable_domains.txt",
        "# Disposable email domains (CC0) from\n"
        "# https://github.com/disposable-email-domains/disposable-email-domains\n",
        disposable_domains(),
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
