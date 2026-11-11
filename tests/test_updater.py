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


class _Response:
    def __init__(self, status, data=None):
        self.status_code = status
        self._data = data or {}

    def json(self):
        return self._data


def _fake_get(answers, seen):
    def get(self, url, timeout=None, **kwargs):
        seen.append((url, self.headers.get("Authorization")))
        return answers[url.rsplit("/repos/", 1)[1]]
    return get


def test_latest_release_is_fetched_without_a_token(monkeypatch):
    seen = []
    answers = {"o/r/releases/latest": _Response(200, release_json())}
    monkeypatch.setattr(updater.requests.Session, "get", _fake_get(answers, seen))
    release = updater.fetch_latest_release(repo="o/r")
    assert release.version == "1.2.0"
    assert seen[0][1] is None  # no Authorization header


def test_repository_without_releases(monkeypatch):
    answers = {"o/r/releases/latest": _Response(404)}
    monkeypatch.setattr(updater.requests.Session, "get", _fake_get(answers, []))
    assert updater.fetch_latest_release(repo="o/r") is None


@pytest.mark.parametrize("status", [403, 429])
def test_rate_limited_check_says_so(monkeypatch, status):
    answers = {"o/r/releases/latest": _Response(status)}
    monkeypatch.setattr(updater.requests.Session, "get", _fake_get(answers, []))
    with pytest.raises(updater.UpdateError, match="limiting"):
        updater.fetch_latest_release(repo="o/r")


def test_server_error_is_reported(monkeypatch):
    answers = {"o/r/releases/latest": _Response(500)}
    monkeypatch.setattr(updater.requests.Session, "get", _fake_get(answers, []))
    with pytest.raises(updater.UpdateError, match="HTTP 500"):
        updater.fetch_latest_release(repo="o/r")
