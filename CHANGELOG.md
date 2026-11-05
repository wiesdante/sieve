# Changelog

All notable changes to Sieve are documented in this file.
The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and the project follows [Semantic Versioning](https://semver.org/).

## [Unreleased]

## [0.13.0] - 2026-11-05

### Changed

- **A new look: a terminal.** Black screen, phosphor green and one monospaced font
  (JetBrains Mono, bundled) everywhere.
  - Every page opens with a prompt (`root@sieve:~$ email_scraper`) and a blinking cursor.
  - Panels are drawn with thin green lines, their titles set into the frame.
  - Square buttons: primary ones in capitals with a soft glow, the rest in lower case.
  - The sidebar lists tools as commands (`> email_scraper`); faint scanlines run over the
    window like an old monitor.
  - A new green icon.
- Statistics lines wrap instead of being cut off on narrow windows.

## [0.12.2] - 2026-11-05

### Removed

- Website Finder's region setting: searches always cover all regions.

## [0.12.1] - 2026-11-05

### Fixed

- **Website Finder searches through your browser (Chrome or Edge).** DuckDuckGo answered
  every plain request with "slow down" (HTTP 202) from the very first search, even from
  home connections, so no company got a result. A real browser gets results; it runs out
  of sight and keeps each connection's cookies like a person searching.
- The window shows what a run is doing while it waits ("DuckDuckGo asked to slow down ·
  waiting 38s"), instead of staying silent until a company is done.
- A media company keeps its own site even when it is a news site (Army Recognition Group →
  armyrecognition.com).
- Country words in a domain no longer count as part of a name: arsenal-usa.com is not
  Bulgaria's Arsenal 2000 JSCo.
- Finance sites such as MarketWatch and Seeking Alpha are never taken for a company's site.
- Quotation marks in a company name no longer reach the search.
- **Use proxies** shows unchecked when the proxy list is empty or turned off.

## [0.12.0] - 2026-11-05

### Added

- **Website Finder** — finds companies' own websites by searching their names on DuckDuckGo.
  - Never takes a company's social media, marketplace, directory, news, job-site, map or
    website-builder page (`name.wixsite.com`, `name.business.site`…) for its website.
    Each kind can be switched off, and your own block lists are saved between sessions.
  - Keeps a result only when it belongs to the company: the domain is spelled by the
    company's name (legal endings such as Ltd., A.Ş. or GmbH ignored), its initials or the
    start of its words (Bird Aerosystems → birdaero.com), or the site's home page title
    names the company (TUSAŞ → tusas.com). The name's leading word must be in the domain,
    so Bird Aerosystems is never aerosystems.com.
  - Close but uncertain candidates are shown as **Unsure** and never mixed into the list.
  - Looks at the first 10 real results and skips ads; reports the site's home page.
  - Recognises DuckDuckGo's bot checks and rate limits, waits and retries, and reports
    **Rate limited** instead of "no website". Only DuckDuckGo's own "No results" counts as
    an empty search.
  - When DuckDuckGo keeps limiting every connection, the remaining companies are reported
    as rate limited within a few minutes instead of waiting on; **Retry failed** puts them
    back in the list for later.
  - Spreads searches over the proxies from Settings, each resting between searches; a
    rate-limited proxy rests longer and a proxy that keeps failing is dropped. Works without
    proxies too, more slowly.
  - Every company keeps its website side by side in the table, in the order entered; the
    same website found for two companies is pointed out. **Checked results** shows every
    result and why it was taken or skipped.

### Changed

- The sidebar lists the scraping tools in the order they are used: Website Finder,
  Link Collector, Email Scraper.
- Domains like `mod.gov.sk` or `depo.gov.pk` are now recognised as separate sites, not as
  part of `gov.sk` or `gov.pk`.

## [0.11.1] - 2026-11-05

### Removed

- Link Collector no longer follows "next page" links. Each page in the list is read on
  its own; for a list split over several pages, enter every page.

### Changed

- Link Collector waits and tries once more when a page answers 502, 503 or 504, which
  sites often send when they are busy or rate-limiting.
- Pages showing very little text next to scripts are opened in the browser in Smart mode,
  since their links are usually drawn by JavaScript.

## [0.11.0] - 2026-11-05

### Added

- **Link Collector** — collects the links on a list of pages, such as directories,
  exhibitor lists or search results, ready to send to Email Scraper.
  - Keep **all** links, only links to **other sites**, or only the **same site**.
  - **Home pages only** turns every link into its site's home page, once per site.
  - Follows **next page** links (`rel="next"`, Next, Sonraki, Weiter, », 다음…) to read
    lists split over several pages, up to a limit you choose.
  - Skips social, share, app-store and map links and file downloads, removes tracking
    parameters (`utm_source`, `fbclid`…) and drops links matching your saved exclude
    rules. Several exclude lists can be kept and switched.
  - Every link comes with its text (often the company name) and the page it was found on.
  - Requests to the same site are spaced out; a site that blocks gets a longer pause and
    one more try. Smart browser mode opens blocked pages, pages built with JavaScript and
    pages without links in your browser.
  - Results are kept when the app closes; **Retry failed** puts blocked and failed pages
    back into the list.

## [0.10.3] - 2026-11-05

### Fixed

- A parking redirect seen only in the browser now marks the site **Parked** instead of
  **No emails**.
- A page that redirects to one already read (`/contact?ref=…` → `/contact/`) is not read again.
- The browser waits when a bot check redirects the page while it is being read, instead of
  failing with "the page is navigating".

### Changed

- The browser keeps a site's cookies from page to page, so a passed bot check or cookie test
  is not repeated on every page. Sites like this are scanned faster and more reliably.
- In Smart mode, a site that times out gets one try in the browser, since some protections
  leave non-browser requests hanging. Refused connections and missing domains are still not
  retried.
- After addresses are found, the scan stops once two more contact pages add nothing new.

## [0.10.2] - 2026-11-05

### Fixed

- **A run no longer hangs on one site, and Stop always works.**
  - A site still loading after 4 minutes is given up and reported as **Failed**, so the
    run always finishes.
  - Stop ends the run within a few seconds, even if a site is in the middle of loading.
  - A server answering "try again in an hour" (`Retry-After`) no longer makes the scan wait.
  - A page whose scripts freeze the browser is given up after a minute, and a fresh browser
    takes over.
- Servers answering 503 now show their page (often a bot check) instead of an error.
- `\n` written out in a page's scripts no longer sticks to the address
  (`ninfo@` → `info@`).
- Template addresses such as `info@website.com` are treated as placeholders.
- A domain that redirects to a parking service (`…?dn=yourdomain.com`) is reported as
  **Parked**.
- Non-standard answers such as HTTP 247 or 492 count as **Blocked** (bot protection).
- When the address entered answers 404, the site's home page is scanned instead.
- The same page is no longer opened twice (with `#…`, `http`/`https`, `www.`), and once a
  contact page has opened its copies in other languages (`/es/…`, `/ru/…`) are skipped.
- News articles whose address happens to contain "contacts" are no longer treated as
  contact pages.
- Contact path guesses no longer carry the site's query string (`?ckattempt=1`).
- A server that does not answer at all is not retried over `http://`.
- **Copy sites table** writes times as `1.3s`, so spreadsheets no longer read them as dates.

### Changed

- The browser no longer identifies itself as automated, which gets past more simple bot checks.
- In Smart mode the browser retry uses a smaller budget (6 pages, 60 seconds), since the
  plain request already looked around.

## [0.10.1] - 2026-11-05

### Changed

- Browser mode now uses **your default browser** when it is Chrome, Edge, Brave or Vivaldi.
  With a browser that cannot be automated (such as Firefox) it uses Chrome, then Edge.
  The log names the browser a site was opened in.

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

[Unreleased]: https://github.com/wiesdante/sieve/compare/v0.13.0...HEAD
[0.13.0]: https://github.com/wiesdante/sieve/compare/v0.12.2...v0.13.0
[0.12.2]: https://github.com/wiesdante/sieve/compare/v0.12.1...v0.12.2
[0.12.1]: https://github.com/wiesdante/sieve/compare/v0.12.0...v0.12.1
[0.12.0]: https://github.com/wiesdante/sieve/compare/v0.11.1...v0.12.0
[0.11.1]: https://github.com/wiesdante/sieve/compare/v0.11.0...v0.11.1
[0.11.0]: https://github.com/wiesdante/sieve/compare/v0.10.3...v0.11.0
[0.10.3]: https://github.com/wiesdante/sieve/compare/v0.10.2...v0.10.3
[0.10.2]: https://github.com/wiesdante/sieve/compare/v0.10.1...v0.10.2
[0.10.1]: https://github.com/wiesdante/sieve/compare/v0.10.0...v0.10.1
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
