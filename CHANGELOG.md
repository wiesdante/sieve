# Changelog

All notable changes to Sieve are documented in this file.
The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and the project follows [Semantic Versioning](https://semver.org/).

## [Unreleased]

## [0.4.0] - 2026-11-02

### Changed

- The whole app is now in English: every page, button, message, the update dialog and the installer.
- Numbers use a comma as the thousands separator (12,345).

## [0.3.1] - 2026-11-02

### Fixed

- Duplicate Remover: the panel buttons (Yapıştır, Boşalt, Girdiye taşı, Duplicate'leri kopyala)
  now look like buttons instead of plain text.
- Disabled primary buttons (e.g. Kopyala before there is a result) now look disabled.

## [0.3.0] - 2026-11-02

### Changed

- **Duplicate Remover** redesigned as a single screen: input and output side by side, options in a
  toolbar and statistics next to the output, so cleaning and copying never require scrolling.
  The divider between the panels can be dragged and its position is remembered.

### Added

- Duplicate Remover: **Yapıştır ve temizle** button that pastes from the clipboard and cleans in one click.
- Duplicate Remover: **Oto. kopyala** option to copy the result to the clipboard as soon as cleaning finishes.
- Duplicate Remover: `Ctrl+Shift+C` copies the result.

### Fixed

- Sidebar section heading no longer looks like a clickable item.
- "GitHub & Updates" settings heading lost its ampersand.

## [0.2.0] - 2026-11-02

### Added

- **Duplicate Remover** tool: paste lines, remove repeated ones and copy the result, all inside the app.
  - Keeps the first occurrence of every line, in its original form and position.
  - Options: case-insensitive matching (with correct Turkish İ/i handling), ignoring
    whitespace differences, removing empty lines, writing normalised output, sorting.
  - Statistics (total, empty, removed, unique) and a list of repeated lines with their counts.
  - Runs in the background with progress and cancel, so large lists don't freeze the window.
- Per-tool preferences are remembered between sessions.

### Changed

- The startup smoke test now opens every tool page.

## [0.1.0] - 2026-11-02

### Added

- Desktop application shell with sidebar navigation and a dark theme.
- Tool registry so each scraping workflow can be added as its own page.
- Settings page with encrypted GitHub token storage, proxy list, rotation mode and proxy health check.
- Automatic update check on startup, with in-app download and silent installation of new releases.
- Windows installer (per-user, no administrator rights required).
- Release pipeline that builds, smoke-tests and publishes the installer whenever the version is bumped.

[Unreleased]: https://github.com/wiesdante/sieve/compare/v0.4.0...HEAD
[0.4.0]: https://github.com/wiesdante/sieve/compare/v0.3.1...v0.4.0
[0.3.1]: https://github.com/wiesdante/sieve/compare/v0.3.0...v0.3.1
[0.3.0]: https://github.com/wiesdante/sieve/compare/v0.2.0...v0.3.0
[0.2.0]: https://github.com/wiesdante/sieve/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/wiesdante/sieve/releases/tag/v0.1.0
