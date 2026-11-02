"""Read the version from ``src/sieve/__init__.py`` without importing the package.

Usage:
    python scripts/project_version.py              print the version
    python scripts/project_version.py --check TAG  fail unless TAG == v<version>
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INIT = ROOT / "src" / "sieve" / "__init__.py"


def read_version() -> str:
    match = re.search(r'^__version__\s*=\s*"([^"]+)"', INIT.read_text(encoding="utf-8"), re.M)
    if not match:
        raise SystemExit("Could not find __version__ in src/sieve/__init__.py")
    return match.group(1)


def main(argv: list[str]) -> int:
    version = read_version()
    if len(argv) == 3 and argv[1] == "--check":
        tag = argv[2].removeprefix("refs/tags/")
        if tag != f"v{version}":
            print(f"Tag {tag} does not match project version v{version}", file=sys.stderr)
            return 1
    print(version)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
