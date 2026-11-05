# Changelog

All notable changes to Sieve are documented in this file.
The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and the project follows [Semantic Versioning](https://semver.org/).

## [Unreleased]

## [0.10.0] - 2026-11-05

### Added

- **Browser mode in Email Scraper** — sites can be opened in the Microsoft Edge that comes with
  Windows (Google Chrome as a fallback), so pages built with JavaScript and simple bot checks
  no longer come back empty. Nothing extra to install.
  - **Smart** (default): a plain request first; the browser only for sites that were blocked,
    had no addresses, only showed a contact form on a JavaScript page, or failed to load.
  - **Always**: every page in the browser. **Off**: plain requests only.
  - Each site keeps its own proxy in the browser too.
  - A new **Via** column shows whether a result came from a plain request or the browser.
- **Contact pages in 25+ languages** — French, Italian, Spanish, Portuguese, Dutch, Polish,
  Czech, Hungarian, Romanian, Serbian/Croatian, Baltic and Nordic languages, Russian, Greek,
  Hebrew, Arabic, Vietnamese, Indonesian, Korean, Japanese and Chinese, alongside English,
  Turkish and German. Links are scored in every language, whatever the site's language.

### Fixed

- Addresses hidden with ROT13 or written backwards are decoded.
- Addresses found only in a site's scripts at another domain (for example a library author's
  address in bundled code) are no longer reported.
- `info@www.example.com` is corrected to `info@example.com`.
- HTTP 401 and 451 answers count as **Blocked** instead of **Failed**.
- A site that times out is no longer retried with every `http`/`www` variant, which took
  over a minute for a single unreachable site.

## [0.9.0] - 2026-11-04

### Changed

- **Email junk filter rebuilt from scratch** with layered checks instead of keyword lists:
  - Addresses must end in a real top-level domain (official IANA list), so file names such as
    `logo@2x.png` are removed without any keyword.
  - Categories that can each be switched off: reserved example domains, placeholder addresses
    in English, Turkish and German, automated senders, disposable inboxes (community list of
    10,000+ domains), service domains (Sentry, Wix, SES, Mailchimp…) and random-looking strings.
  - Random-looking detection no longer depends on length, so long real names such as
    `datenschutzbeauftragter@` are kept.
  - Your own block and allow lists accept addresses, domains (with subdomains) and usernames.
  - Optional **MX check** verifies that each domain exists and accepts email.
  - The previous built-in keyword lists, which removed real addresses at domains containing
    words like "media" or "image" and usernames like "privacy" or "webmaster", are gone.
- **Email Scraper finds contact pages much more reliably**:
  - Links are ranked by how likely they lead to contact or legal pages in English, Turkish and
    German: Impressum, Kontakt, Datenschutz, İletişim, KVKK, Künye, Contact, Imprint…
  - Reads addresses published as schema.org data and uses the site's sitemap to find contact
    pages that are not linked from the first page.
  - Visits pages in order of promise within a budget of 8 requests per site and stops early
    once a contact page has given an address.
  - Guesses common paths in the site's language (`/impressum`, `/kontakt`, `/iletisim`, `/kvkk`…)
    only as a last resort.
  - Subdomains such as `destek.firma.com.tr` count as the same site.
  - Tries the `www.` / bare domain variant when a site cannot be reached.
  - New statuses: **Form only** (no address, just a contact form), **Parked** (parked or
    for-sale domain) and **Blocked** (bot protection or captcha). Blocked sites are included
    in **Retry failed**.
  - Email details show how each address was found, including site data and the page source.

### Added

- **Send to**: pass any tool's result straight into another tool's input.
- Keyword Filter and Text Stripper: **several saved lists** per tool (new, rename, duplicate,
  delete), kept across updates. Existing lists become the "Default" list.
- Keyword Filter and Text Stripper: **Regex** option.
- Duplicate Remover: **Compare as URLs** treats http/https, `www.` and a trailing slash as the same.
- The taskbar button flashes when a long scan or extraction finishes in the background.
- `(at)`/`[at]` and `(dot)`/`(punkt)`/`(nokta)` obfuscation is decoded in German and Turkish too.
- Reference lists (top-level domains, disposable inboxes) are refreshed automatically every month.

## [0.8.0] - 2026-11-04

### Added

- **Email Scraper** tool: paste a list of websites and collect their contact email addresses.
  - **Standard** mode scans each site's page, visits the two pages that look most like a
    contact page, and if nothing was found tries common paths such as `/contact` and
    `/iletisim` (also inside language folders like `/tr/`). **Direct** mode scans only the
    URLs you entered.
  - Finds addresses in the page text and source, `mailto:` links, Cloudflare-protected
    addresses, `(at)`/`[dot]` obfuscation, URL-encoded and escaped addresses, and in the
    site's own scripts.
  - Falls back from HTTPS to HTTP when the secure connection fails.
  - Scans several sites at once and can use the proxy list from Settings, one proxy per site.
  - Results appear live: unique emails, email details (site, page, how it was found), a
    per-site table with status and errors, rejected addresses with the reason, and a log.
  - **Stop** finishes the sites in progress; **Retry failed** puts failed sites back in the list.
  - The last scan is saved automatically and restored when the app opens again.
- **Junk filter** for email addresses, shared by Email Scraper and Link & Email Extractor:
  removes placeholders, no-reply and system senders, disposable inboxes, tracking and CDN
  domains, image names and token-like addresses. Every list can be edited under **Rules...**
  and is kept across updates.
- Link & Email Extractor: **Filter junk** option and a **Rejected** tab in Emails mode, so a
  raw list of addresses can be cleaned by pasting it into the Text tab.

### Changed

- Email extraction now also decodes `%40`, `\u0040` and `(at)`/`[dot]` forms.
- Email Scraper and Link & Email Extractor are listed first in the sidebar.

## [0.7.0] - 2026-11-04

### Added

- **Link & Email Extractor** tool: collect web links or email addresses from one or more PDF
  files (drag and drop or Add PDFs...) or from pasted text.
  - **Links** mode combines clickable links with addresses written in the text
    (`https://...`, `www....` and optionally bare domains such as `example.com`).
    File names like `report.pdf` and sentences without a space after the full stop are ignored.
  - **Emails** mode combines `mailto:` links with addresses written in the text.
    Image names like `logo@2x.png` are ignored.
  - Duplicates are removed: for links, http/https, `www.`, letter case in the domain and a
    trailing slash do not matter; for emails, letter case does not matter.
  - **Domains only** outputs just the site of each link or the domain of each email.
  - **Details** shows the file, page and kind of every result and can be copied as a table.
  - Password-protected or damaged PDFs are listed under **Problems**; the other files are
    still processed.

### Changed

- Release builds now check that every tool's dependencies are included before publishing.

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

[Unreleased]: https://github.com/wiesdante/sieve/compare/v0.10.0...HEAD
[0.10.0]: https://github.com/wiesdante/sieve/compare/v0.9.0...v0.10.0
[0.9.0]: https://github.com/wiesdante/sieve/compare/v0.8.0...v0.9.0
[0.8.0]: https://github.com/wiesdante/sieve/compare/v0.7.0...v0.8.0
[0.7.0]: https://github.com/wiesdante/sieve/compare/v0.6.0...v0.7.0
[0.6.0]: https://github.com/wiesdante/sieve/compare/v0.5.0...v0.6.0
[0.5.0]: https://github.com/wiesdante/sieve/compare/v0.4.1...v0.5.0
[0.4.1]: https://github.com/wiesdante/sieve/compare/v0.4.0...v0.4.1
[0.4.0]: https://github.com/wiesdante/sieve/compare/v0.3.1...v0.4.0
[0.3.1]: https://github.com/wiesdante/sieve/compare/v0.3.0...v0.3.1
[0.3.0]: https://github.com/wiesdante/sieve/compare/v0.2.0...v0.3.0
[0.2.0]: https://github.com/wiesdante/sieve/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/wiesdante/sieve/releases/tag/v0.1.0
