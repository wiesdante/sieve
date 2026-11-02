"""Self-update support backed by GitHub Releases of a private repository.

The flow is:

1. ``fetch_latest_release`` asks the GitHub API for the latest release,
   authenticated with the user's fine-grained token (read-only Contents).
2. If it is newer than the running version, ``download_installer`` streams the
   ``Sieve-Setup-<version>.exe`` asset to the local updates folder and verifies
   its size and SHA-256 digest.
3. ``launch_installer`` starts the installer in silent mode and the app quits.
   The installer closes any running instance, replaces the files and starts
   the new version.
"""

from __future__ import annotations

import hashlib
import logging
import subprocess
import sys
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import requests
from packaging.version import InvalidVersion, Version

from sieve import GITHUB_REPO, __version__, paths

log = logging.getLogger(__name__)

API_ROOT = "https://api.github.com"
ASSET_PREFIX = "Sieve-Setup-"
ASSET_SUFFIX = ".exe"
TIMEOUT = 20

ProgressCallback = Callable[[int, int], None]
CancelCheck = Callable[[], bool]


class UpdateError(Exception):
    """Any failure while checking for or downloading an update."""


class AuthError(UpdateError):
    """The token is missing, invalid or lacks access to the repository."""


class UpdateCancelledError(UpdateError):
    pass


@dataclass(frozen=True)
class ReleaseInfo:
    version: str
    tag: str
    notes: str
    html_url: str
    asset_id: int
    asset_name: str
    asset_size: int
    sha256: str | None = None


def parse_version(text: str) -> Version:
    try:
        return Version(text.strip().lstrip("vV"))
    except InvalidVersion as exc:
        raise UpdateError(f"Geçersiz sürüm numarası: {text}") from exc


def is_newer(candidate: str, current: str = __version__) -> bool:
    return parse_version(candidate) > parse_version(current)


def _session(token: str) -> requests.Session:
    session = requests.Session()
    session.headers.update({
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": f"Sieve/{__version__}",
        "Authorization": f"Bearer {token}",
    })
    return session


def _raise_for_status(response: requests.Response) -> None:
    if response.status_code == 401:
        raise AuthError("GitHub token geçersiz veya süresi dolmuş.")
    if response.status_code == 403:
        raise AuthError("GitHub isteği reddetti. Token izinlerini kontrol et.")
    if response.status_code >= 400:
        raise UpdateError(f"GitHub beklenmeyen bir yanıt döndü (HTTP {response.status_code}).")


def _request(session: requests.Session, url: str, **kwargs) -> requests.Response:
    try:
        return session.get(url, timeout=TIMEOUT, **kwargs)
    except requests.RequestException as exc:
        raise UpdateError("GitHub'a bağlanılamadı. İnternet bağlantını kontrol et.") from exc


def verify_token(token: str, repo: str = GITHUB_REPO) -> str:
    """Return the repository's full name if the token can read it."""
    with _session(token) as session:
        response = _request(session, f"{API_ROOT}/repos/{repo}")
    if response.status_code == 404:
        raise AuthError("Token'ın bu repoya erişimi yok.")
    _raise_for_status(response)
    return response.json().get("full_name", repo)


def release_from_json(data: dict) -> ReleaseInfo:
    tag = str(data.get("tag_name") or "")
    version = str(parse_version(tag))
    for asset in data.get("assets") or []:
        name = str(asset.get("name") or "")
        if name.startswith(ASSET_PREFIX) and name.endswith(ASSET_SUFFIX):
            digest = asset.get("digest") or ""
            sha256 = digest.split(":", 1)[1].lower() if digest.startswith("sha256:") else None
            return ReleaseInfo(
                version=version,
                tag=tag,
                notes=str(data.get("body") or ""),
                html_url=str(data.get("html_url") or ""),
                asset_id=int(asset["id"]),
                asset_name=name,
                asset_size=int(asset.get("size") or 0),
                sha256=sha256,
            )
    raise UpdateError(f"{tag} sürümünde kurulum dosyası bulunamadı.")


def fetch_latest_release(token: str, repo: str = GITHUB_REPO) -> ReleaseInfo | None:
    """Return the latest published release, or ``None`` if there is none yet."""
    with _session(token) as session:
        response = _request(session, f"{API_ROOT}/repos/{repo}/releases/latest")
        if response.status_code == 404:
            # Either no release exists yet or the token cannot see the repo.
            verify_token(token, repo)
            return None
        _raise_for_status(response)
        return release_from_json(response.json())


def download_installer(
    release: ReleaseInfo,
    token: str,
    repo: str = GITHUB_REPO,
    progress: ProgressCallback | None = None,
    cancelled: CancelCheck | None = None,
) -> Path:
    target = paths.updates_dir() / release.asset_name
    partial = target.with_suffix(target.suffix + ".part")
    url = f"{API_ROOT}/repos/{repo}/releases/assets/{release.asset_id}"

    digest = hashlib.sha256()
    received = 0
    with _session(token) as session:
        # The API answers with a redirect to a storage host; requests drops the
        # Authorization header when following it, which is what GitHub expects.
        response = _request(
            session, url, headers={"Accept": "application/octet-stream"}, stream=True
        )
        with response:
            _raise_for_status(response)
            total = int(response.headers.get("Content-Length") or release.asset_size or 0)
            with partial.open("wb") as handle:
                for chunk in response.iter_content(chunk_size=256 * 1024):
                    if cancelled and cancelled():
                        handle.close()
                        partial.unlink(missing_ok=True)
                        raise UpdateCancelledError("İndirme iptal edildi.")
                    handle.write(chunk)
                    digest.update(chunk)
                    received += len(chunk)
                    if progress:
                        progress(received, total)

    if release.asset_size and received != release.asset_size:
        partial.unlink(missing_ok=True)
        raise UpdateError("İndirilen dosya eksik. Lütfen tekrar dene.")
    if release.sha256 and digest.hexdigest() != release.sha256:
        partial.unlink(missing_ok=True)
        raise UpdateError("İndirilen dosya doğrulanamadı (SHA-256 uyuşmuyor).")

    partial.replace(target)
    log.info("Downloaded %s (%d bytes)", target.name, received)
    return target


def launch_installer(installer: Path) -> None:
    """Run the installer silently; the caller must quit the app right after."""
    if sys.platform != "win32":
        raise UpdateError("Otomatik kurulum yalnızca Windows'ta desteklenir.")
    flags = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
    subprocess.Popen(
        [str(installer), "/SILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/CLOSEAPPLICATIONS"],
        creationflags=flags,
        close_fds=True,
    )
    log.info("Started installer %s", installer.name)


def clean_old_downloads() -> None:
    """Remove installers left over from previous updates."""
    for item in paths.updates_dir().iterdir():
        try:
            item.unlink()
        except OSError:
            log.debug("Could not remove %s", item)
