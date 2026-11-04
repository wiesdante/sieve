"""HttpFetcher against a real HTTP server on localhost."""

import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from sieve.core.email_filter import EmailFilter
from sieve.core.email_scraper import FOUND, HttpFetcher, scan_site

pytest.importorskip("bs4")

PAGES = {
    "/": ("text/html; charset=utf-8", '<a href="/iletisim">İletişim</a> Hoş geldiniz'.encode()),
    "/iletisim": ("text/html", "Bize yazın: satis@örnek.com.tr, info@acme.test.example".encode()),
    "/latin": ("text/html; charset=iso-8859-9", "E-posta: bilgi@acme.com.tr - Şirket".encode("iso-8859-9")),
    "/logo.png": ("image/png", b"\x89PNG..."),
}


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):  # noqa: N802
        if self.path == "/old":
            self.send_response(301)
            self.send_header("Location", "/latin")
            self.end_headers()
            return
        if self.path not in PAGES:
            self.send_response(404)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(b"missing")
            return
        content_type, body = PAGES[self.path]
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


@pytest.fixture(scope="module")
def server():
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{httpd.server_address[1]}"
    httpd.shutdown()


def test_fetch_page_and_decode(server):
    page = HttpFetcher().fetch(server + "/")
    assert page.ok and page.status == 200
    assert "Hoş geldiniz" in page.text


def test_declared_charset_is_respected_and_redirects_followed(server):
    page = HttpFetcher().fetch(server + "/old")
    assert page.url.endswith("/latin")
    assert "Şirket" in page.text


def test_non_text_content_is_skipped(server):
    page = HttpFetcher().fetch(server + "/logo.png")
    assert not page.ok and "Not a web page" in page.error


def test_missing_page_reports_status(server):
    page = HttpFetcher().fetch(server + "/nope")
    assert page.status == 404


def test_full_site_scan(server):
    result = scan_site(server, HttpFetcher(), EmailFilter())
    assert result.status == FOUND
    assert [found.email for found in result.emails] == ["satis@örnek.com.tr"]
    assert result.emails[0].page.endswith("/iletisim")


def test_connection_refused_is_reported():
    page = HttpFetcher().fetch("http://127.0.0.1:9/")
    assert not page.ok and page.error
