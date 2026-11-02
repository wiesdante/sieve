"""Print the CHANGELOG.md section for a version (used as GitHub release notes).

Usage: python scripts/release_notes.py 0.1.0
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

CHANGELOG = Path(__file__).resolve().parents[1] / "CHANGELOG.md"


def extract(changelog: str, version: str) -> str:
    pattern = re.compile(rf"^## \[{re.escape(version)}\][^\n]*\n(.*?)(?=^## \[|\Z)", re.M | re.S)
    match = pattern.search(changelog)
    if not match:
        raise LookupError(f"No CHANGELOG entry for {version}")
    body = re.sub(r"^\[[^\]]+\]:\s*\S+\s*$", "", match.group(1), flags=re.M)
    return body.strip() + "\n"


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print(__doc__, file=sys.stderr)
        return 2
    try:
        print(extract(CHANGELOG.read_text(encoding="utf-8"), argv[1].lstrip("v")), end="")
    except LookupError as exc:
        print(exc, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
