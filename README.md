<p align="center">
  <img src="assets/icon.png" width="96" alt="Sieve logo">
</p>

<h1 align="center">Sieve</h1>

<p align="center">
  A desktop toolkit that brings data scraping workflows together in one app.<br>
  <sub>by <b>wiesdante</b></sub>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/platform-Windows%2010%20%7C%2011-0078D6" alt="Platform">
  <img src="https://img.shields.io/badge/python-3.12-3776AB" alt="Python">
</p>

---

Sieve replaces a folder full of one-off console scripts with a single desktop
application. Each workflow lives in the app as a **tool** with its own page,
and every tool shares the same settings, proxy pool and logging.

## Tools

| Tool | What it does |
| --- | --- |
| **Duplicate Remover** | Removes repeated lines from pasted text while keeping the first occurrence and the original order. |
| **Keyword Filter** | Keeps or removes lines that contain any keyword from a saved blacklist or whitelist. |
| **Text Stripper** | Removes saved phrases such as labels and prefixes (`Email: `, `Phone: `) from every line. |
| **Link & Email Extractor** | Collects web links or email addresses from PDF files (clickable links and text) or pasted text. |

## Features

- **One app, many tools** — every scraping workflow gets its own page in the sidebar.
- **Shared proxy pool** — configure proxies once (HTTP, HTTPS, SOCKS4/5, with or
  without credentials), test them from the app, and let tools rotate through them.
- **Self-updating** — Sieve checks the latest GitHub release on startup and can
  download and install it in place, no manual setup needed.
- **No dependencies on the target PC** — the installer ships everything, including
  the Python runtime. Browser automation uses the Microsoft Edge that comes with Windows.
- **Per-user install** — installs under `%LOCALAPPDATA%`, no administrator rights required.

## Installation

1. Open the [latest release](https://github.com/wiesdante/sieve/releases/latest)
   and download `Sieve-Setup-<version>.exe`.
2. Run it. Because the installer is not code-signed, Windows SmartScreen may show
   a warning: choose **More info → Run anyway**.
3. Launch Sieve from the Start menu or the desktop shortcut.

### Enabling automatic updates

The repository is private, so Sieve needs a read-only GitHub token to see new releases:

1. GitHub → **Settings → Developer settings → Personal access tokens → Fine-grained tokens → Generate new token**.
2. **Repository access:** *Only select repositories* → `wiesdante/sieve`.
3. **Permissions → Repository permissions → Contents:** *Read-only*.
4. Paste the token into **Settings → GitHub & Updates** in Sieve and click **Save & test**.

The token is encrypted with Windows DPAPI and can only be read by your Windows
user on that machine.

## Data locations

| What | Where |
| --- | --- |
| Application | `%LOCALAPPDATA%\Programs\Sieve` |
| Settings & encrypted credentials | `%APPDATA%\Sieve` |
| Logs | `%LOCALAPPDATA%\Sieve\logs` |
| Downloaded updates | `%LOCALAPPDATA%\Sieve\updates` |

Uninstalling Sieve keeps your settings; delete `%APPDATA%\Sieve` to remove them too.

## Development

Requirements: Python 3.12 on Windows (the UI also runs on macOS/Linux for development).

```powershell
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements-dev.txt
python -m sieve          # run from source (with PYTHONPATH=src, or `pip install -e .`)
pytest                   # tests
ruff check .             # lint
```

Building a local installer (requires [Inno Setup 6](https://jrsoftware.org/isinfo.php)):

```powershell
python scripts/make_version_info.py
pyinstaller sieve.spec --noconfirm --clean
& "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe" /DAppVersion=0.1.0 installer\sieve.iss
```

More documentation:

- [Adding a tool](docs/adding-a-tool.md)
- [Release process](docs/releasing.md)

## Project structure

```
src/sieve/
├── app.py            application bootstrap
├── updater.py        GitHub Releases update logic
├── proxy.py          proxy parsing, rotation and health checks
├── settings.py       persistent settings (JSON)
├── credentials.py    DPAPI-encrypted secrets
├── tools/            the tools shown in the sidebar
└── ui/               main window, pages, theme and update dialogs
installer/sieve.iss   Inno Setup installer script
sieve.spec            PyInstaller build definition
scripts/              build and release helpers
tests/                unit tests
```

## License

Proprietary — all rights reserved. See [LICENSE](LICENSE).
