"""Scan a few sites with the real scraper and print the full log (used by CI).

Usage: python scripts/live_check.py [--browser smart|always|off] SITE [SITE ...]
       python scripts/live_check.py --links [--pages N] [--external] [--home] PAGE [PAGE ...]
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from sieve.core.email_filter import EmailFilter  # noqa: E402
from sieve.core.email_scraper import (  # noqa: E402
    BROWSER_MODES,
    HttpFetcher,
    ScrapeOptions,
    scrape_sites,
)


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser()
    parser.add_argument("--browser", choices=BROWSER_MODES, default="smart")
    parser.add_argument("--links", action="store_true", help="run Link Collector instead")
    parser.add_argument("--pages", type=int, default=1, help="pages to read per entry (Link Collector)")
    parser.add_argument("--external", action="store_true", help="only links to other sites")
    parser.add_argument("--home", action="store_true", help="home pages only")
    parser.add_argument("sites", nargs="+")
    args = parser.parse_args()
    if args.links:
        return check_links(args)

    options = ScrapeOptions(workers=min(10, len(args.sites)), browser=args.browser)
    browsers = None
    browser_for = None
    if args.browser != "off":
        from sieve.core.browser import BrowserFetcher, BrowserPool

        browsers = BrowserPool(size=3)
        browser_for = lambda _index: BrowserFetcher(browsers)  # noqa: E731

    started = time.monotonic()
    try:
        summary = scrape_sites(args.sites, lambda _index: HttpFetcher(), EmailFilter(), options,
                               browser_for=browser_for)
    finally:
        if browsers:
            browsers.close()
    for result in summary.results:
        print(f"\n── {result.site}")
        print("\n".join(result.log))
        print(f"=> {result.status} via {result.via}: {', '.join(f.email for f in result.emails) or '-'}"
              + (f" ({result.error})" if result.error else ""))
    print(f"\nFinished {len(summary.results)}/{len(args.sites)} sites in {time.monotonic() - started:.1f}s")
    return 0


def check_links(args) -> int:
    from sieve.core.link_collector import (
        EXTERNAL,
        CollectOptions,
        LinkFilterSettings,
        collect_links,
    )

    filters = LinkFilterSettings(scope=EXTERNAL if args.external else "all", home_pages_only=args.home)
    options = CollectOptions(filters=filters, workers=min(5, len(args.sites)), browser=args.browser,
                             max_pages=args.pages)
    browsers = None
    browser_for = None
    if args.browser != "off":
        from sieve.core.browser import BrowserFetcher, BrowserPool

        browsers = BrowserPool(size=2)
        browser_for = lambda _index: BrowserFetcher(browsers)  # noqa: E731
    started = time.monotonic()
    try:
        summary = collect_links(args.sites, lambda _index: HttpFetcher(), options, browser_for=browser_for)
    finally:
        if browsers:
            browsers.close()
    for result in summary.results:
        print(f"\n── {result.url}")
        print("\n".join(result.log))
        print(f"=> {result.status} via {result.via}: {len(result.links)} links kept, "
              f"{len(result.rejected)} filtered out" + (f" ({result.error})" if result.error else ""))
        for link in result.links[:15]:
            print(f"   {link.url}  [{link.text}]")
        if len(result.links) > 15:
            print(f"   ... {len(result.links) - 15} more")
        reasons: dict[str, int] = {}
        for _url, reason in result.rejected:
            reasons[reason] = reasons.get(reason, 0) + 1
        if reasons:
            print("   filtered: " + ", ".join(f"{reason} ×{count}" for reason, count in reasons.items()))
    print(f"\nFinished {len(summary.results)}/{len(args.sites)} pages in {time.monotonic() - started:.1f}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
