import pytest

from sieve import updater


def release_json(tag="v1.2.0", assets=None):
    if assets is None:
        assets = [
            {"id": 1, "name": "notes.txt", "size": 10},
            {
                "id": 42,
                "name": f"Sieve-Setup-{tag.lstrip('v')}.exe",
                "size": 1234,
                "digest": "sha256:ABCDEF",
            },
        ]
    return {
        "tag_name": tag,
        "body": "## Added\n- Something",
        "html_url": "https://github.com/wiesdante/sieve/releases/tag/" + tag,
        "assets": assets,
    }


@pytest.mark.parametrize(
    ("candidate", "current", "expected"),
    [
        ("v0.2.0", "0.1.0", True),
        ("0.1.1", "0.1.0", True),
        ("v0.1.0", "0.1.0", False),
        ("0.0.9", "0.1.0", False),
        ("1.0.0", "1.0.0rc1", True),
        ("0.10.0", "0.9.0", True),
    ],
)
def test_is_newer(candidate, current, expected):
    assert updater.is_newer(candidate, current) is expected


def test_invalid_version_raises_update_error():
    with pytest.raises(updater.UpdateError):
        updater.parse_version("latest")


def test_release_from_json_picks_installer_asset():
    info = updater.release_from_json(release_json())
    assert info.version == "1.2.0"
    assert info.tag == "v1.2.0"
    assert info.asset_id == 42
    assert info.asset_name == "Sieve-Setup-1.2.0.exe"
    assert info.asset_size == 1234
    assert info.sha256 == "abcdef"
    assert "Something" in info.notes


def test_release_without_digest():
    data = release_json(assets=[{"id": 7, "name": "Sieve-Setup-1.2.0.exe", "size": 5}])
    assert updater.release_from_json(data).sha256 is None


def test_release_without_installer_raises():
    with pytest.raises(updater.UpdateError):
        updater.release_from_json(release_json(assets=[{"id": 1, "name": "source.zip"}]))


def test_clean_old_downloads(isolated_home):
    from sieve import paths

    leftover = paths.updates_dir() / "Sieve-Setup-0.0.1.exe"
    leftover.write_bytes(b"x")
    updater.clean_old_downloads()
    assert not leftover.exists()
