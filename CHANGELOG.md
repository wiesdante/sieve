# Changelog

All notable changes to Sieve are documented in this file.
The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and the project follows [Semantic Versioning](https://semver.org/).

## [Unreleased]

## [0.6.0] - 2026-11-04

### Added

- **Text Stripper** tool: remove saved phrases such as labels and prefixes from every line,
  for example turning `Email: john@example.com` into `john@example.com`.
  - The phrase list is saved automatically and survives restarts and updates.
  - Spaces are shown in the phrase list, since a trailing space is part of a phrase.
  - Phrases are matched literally and applied in one pass, longest first.
  - Options: ignore case (with correct Turkish İ/i handling), trim lines, drop lines that
    become empty.
  - See how many times each phrase was removed, including phrases that never matched.

## [0.5.0] - 2026-11-02

### Added

- **Keyword Filter** tool: filter pasted text with a blacklist (remove lines that contain a
  keyword) or a whitelist (keep only lines that contain a keyword).
  - Both lists are saved automatically and survive restarts and updates.
  - Options: ignore case (with correct Turkish İ/i handling), whole words only, skip empty lines.
  - See the removed lines and how many lines each keyword matched, including keywords that
    matched nothing.
- The sidebar collapses to an icon rail while a tool is open, giving the tool the full width.
  Use the button at the top to expand it and switch tools.
- Icons for every sidebar item.

### Changed

- New application icon.

## [0.4.1] - 2026-11-02

### Fixed

- Duplicate Remover: option labels in the toolbar were cut off in smaller windows.

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

[Unreleased]: https://github.com/wiesdante/sieve/compare/v0.6.0...HEAD
[0.6.0]: https://github.com/wiesdante/sieve/compare/v0.5.0...v0.6.0
[0.5.0]: https://github.com/wiesdante/sieve/compare/v0.4.1...v0.5.0
[0.4.1]: https://github.com/wiesdante/sieve/compare/v0.4.0...v0.4.1
[0.4.0]: https://github.com/wiesdante/sieve/compare/v0.3.1...v0.4.0
[0.3.1]: https://github.com/wiesdante/sieve/compare/v0.3.0...v0.3.1
[0.3.0]: https://github.com/wiesdante/sieve/compare/v0.2.0...v0.3.0
[0.2.0]: https://github.com/wiesdante/sieve/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/wiesdante/sieve/releases/tag/v0.1.0
