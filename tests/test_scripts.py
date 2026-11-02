import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import project_version  # noqa: E402
import release_notes  # noqa: E402
from sieve import __version__  # noqa: E402

CHANGELOG = """# Changelog

## [Unreleased]

## [0.2.0] - 2026-12-01
### Added
- Second

## [0.1.0] - 2026-11-02
### Added
- First

[0.2.0]: https://example.com/0.2.0
"""


def test_extract_release_notes():
    assert release_notes.extract(CHANGELOG, "0.2.0") == "### Added\n- Second\n"
    assert release_notes.extract(CHANGELOG, "0.1.0").startswith("### Added\n- First")


def test_extract_missing_version():
    import pytest

    with pytest.raises(LookupError):
        release_notes.extract(CHANGELOG, "9.9.9")


def test_project_version_matches_package():
    assert project_version.read_version() == __version__
    assert project_version.main(["x", "--check", f"v{__version__}"]) == 0
    assert project_version.main(["x", "--check", "v999.0.0"]) == 1
