"""BrowserPool against a local page in a real Edge/Chrome (Windows CI only)."""

import os
import threading
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


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):  # noqa: N802
        body = APP_PAGE if self.path == "/" else b"missing"
        self.send_response(200 if self.path == "/" else 404)
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
