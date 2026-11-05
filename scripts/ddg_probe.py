"""Try several ways of searching DuckDuckGo and print what each one gets (used by CI)."""

from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from sieve.core.website_finder import parse_search_page  # noqa: E402

QUERIES = ["Aselsan", "Bird Aerosystems", "Excalibur Army"]
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36")


def show(name: str, status: int, html: str) -> None:
    page = parse_search_page(status, html)
    first = page.results[0].url if page.results else ""
    print(f"{name:38} HTTP {status:<4} {page.kind:11} {len(page.results):>2} results {first}", flush=True)


def with_requests() -> None:
    import requests

    session = requests.Session()
    session.headers.update({"User-Agent": UA, "Accept-Language": "en-US,en;q=0.9"})
    for query in QUERIES:
        r = session.post("https://html.duckduckgo.com/html/", data={"q": query, "b": ""}, timeout=20,
                         headers={"Referer": "https://html.duckduckgo.com/"})
        show(f"requests POST html {query}", r.status_code, r.text)
        time.sleep(3)
        r = session.get("https://html.duckduckgo.com/html/", params={"q": query}, timeout=20)
        show(f"requests GET html {query}", r.status_code, r.text)
        time.sleep(3)
        r = session.post("https://lite.duckduckgo.com/lite/", data={"q": query}, timeout=20)
        show(f"requests POST lite {query}", r.status_code, r.text)
        time.sleep(3)


def with_curl_cffi() -> None:
    try:
        from curl_cffi import requests as curl
    except ImportError:
        print("curl_cffi not installed")
        return
    session = curl.Session(impersonate="chrome")
    for query in QUERIES:
        r = session.post("https://html.duckduckgo.com/html/", data={"q": query, "b": ""}, timeout=20)
        show(f"curl_cffi POST html {query}", r.status_code, r.text)
        time.sleep(3)
        r = session.post("https://lite.duckduckgo.com/lite/", data={"q": query}, timeout=20)
        show(f"curl_cffi POST lite {query}", r.status_code, r.text)
        time.sleep(3)


def with_browser() -> None:
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        for channel in ("chrome", "msedge"):
            try:
                browser = p.chromium.launch(channel=channel, headless=True,
                                            args=["--disable-blink-features=AutomationControlled"])
                break
            except Exception as exc:  # noqa: BLE001
                print(f"{channel}: {exc}")
        else:
            return
        agent = browser.new_page().evaluate("navigator.userAgent").replace("HeadlessChrome", "Chrome")
        context = browser.new_context(user_agent=agent, locale="en-US")
        page = context.new_page()
        for query in QUERIES:
            response = page.goto(f"https://html.duckduckgo.com/html/?q={query}", wait_until="domcontentloaded")
            show(f"browser GET html {query}", response.status if response else 0, page.content())
            time.sleep(3)
            response = page.goto(f"https://lite.duckduckgo.com/lite/?q={query}", wait_until="domcontentloaded")
            show(f"browser GET lite {query}", response.status if response else 0, page.content())
            time.sleep(3)
        browser.close()


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", line_buffering=True)
    for step in (with_requests, with_curl_cffi, with_browser):
        try:
            step()
        except Exception as exc:  # noqa: BLE001
            print(f"{step.__name__} failed: {exc}")
