"""BrowserPool against a local page in a real Edge/Chrome (Windows CI only)."""

import os
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

if os.environ.get("SIEVE_BROWSER_TESTS") != "1":
    pytest.skip("browser tests run only with SIEVE_BROWSER_TESTS=1", allow_module_level=True)

pytest.importorskip("playwright")

from sieve.core.browser import BrowserFetcher, BrowserPool  # noqa: E402
from sieve.core.email_scraper import (  # noqa: E402
    BROWSER_SMART,
    EMPTY,
    FOUND,
    HttpFetcher,
    ScrapeOptions,
    scan_site,
)

APP_PAGE = b"""<!doctype html><html lang="en"><head><title>App</title></head>
<body><div id="root"></div>
<script>
  setTimeout(function () {
    var user = ["hello", "rendered"].join("@");
    document.getElementById("root").innerHTML =
      '<p>Contact us: ' + user + '.example.com</p>';
  }, 300);
</script></body></html>"""


FROZEN_PAGE = b"""<!doctype html><html><body><p>Loading</p>
<script>setTimeout(function () { while (true) {} }, 50);</script></body></html>"""
WHO_PAGE = b"""<!doctype html><html><body><p id="who"></p>
<script>document.getElementById("who").textContent =
  navigator.userAgent + " webdriver=" + navigator.webdriver;</script></body></html>"""
ROUTES = {"/": APP_PAGE, "/frozen": FROZEN_PAGE, "/who": WHO_PAGE}


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):  # noqa: N802
        body = ROUTES.get(self.path, b"missing")
        self.send_response(200 if self.path in ROUTES else 404)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


@pytest.fixture(scope="module")
def server():
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{httpd.server_address[1]}"
    httpd.shutdown()


@pytest.fixture(scope="module")
def pool():
    browsers = BrowserPool(size=2)
    yield browsers
    browsers.close()


def test_browser_runs_scripts(server, pool):
    result = BrowserFetcher(pool).fetch(server + "/")
    assert pool.available, pool.error
    assert result.status == 200
    assert "hello@rendered.example.com" in result.text


def test_plain_request_misses_script_content(server):
    plain = scan_site(server, HttpFetcher(), options=ScrapeOptions(browser="off"))
    assert plain.status == EMPTY


def test_smart_mode_finds_script_content(server, pool):
    result = scan_site(server, HttpFetcher(), options=ScrapeOptions(browser=BROWSER_SMART),
                       browser=BrowserFetcher(pool))
    assert result.status == FOUND, result.log
    assert result.via == "browser"
    assert [found.email for found in result.emails] == ["hello@rendered.example.com"]


def test_default_browser_is_read_and_named(pool):
    from sieve.core.browser import default_browser

    default_browser()  # must not raise on Windows
    assert pool.name in ("Google Chrome", "Microsoft Edge", "Brave", "Vivaldi", "Chromium")


def test_browser_does_not_announce_automation(server, pool):
    result = BrowserFetcher(pool).fetch(server + "/who")
    assert "HeadlessChrome" not in result.text
    assert "webdriver=true" not in result.text


def test_frozen_page_is_given_up_and_the_pool_keeps_working(server, monkeypatch):
    from sieve.core import browser as browser_module

    monkeypatch.setattr(browser_module, "PAGE_TIMEOUT", 8.0)
    single = BrowserPool(size=1)
    try:
        started = time.monotonic()
        frozen = BrowserFetcher(single).fetch(server + "/frozen")
        assert time.monotonic() - started < 15
        assert frozen.error == "Browser timed out"
        after = BrowserFetcher(single).fetch(server + "/")
        assert "hello@rendered.example.com" in after.text
    finally:
        started = time.monotonic()
        single.close()
        assert time.monotonic() - started < 7
