import pytest

from sieve.proxy import Proxy, ProxyParseError, ProxyPool, parse_proxy, parse_proxy_list


@pytest.mark.parametrize(
    ("line", "expected"),
    [
        ("1.2.3.4:8080", Proxy("http", "1.2.3.4", 8080)),
        ("1.2.3.4:8080:user:pass", Proxy("http", "1.2.3.4", 8080, "user", "pass")),
        ("1.2.3.4:8080:user:pa:ss", Proxy("http", "1.2.3.4", 8080, "user", "pa:ss")),
        ("user:pass@proxy.example.com:3128", Proxy("http", "proxy.example.com", 3128, "user", "pass")),
        ("http://u%40x:p@host:80", Proxy("http", "host", 80, "u@x", "p")),
        ("socks5://10.0.0.1:1080", Proxy("socks5", "10.0.0.1", 1080)),
        ("  host:1  ", Proxy("http", "host", 1)),
    ],
)
def test_parse_proxy(line, expected):
    assert parse_proxy(line) == expected


@pytest.mark.parametrize("line", ["", "host", "host:port", "host:0", "host:70000", "ftp://h:21", "a:1:b"])
def test_parse_proxy_rejects_invalid(line):
    with pytest.raises(ProxyParseError):
        parse_proxy(line)


def test_proxy_urls_escape_credentials():
    proxy = Proxy("http", "host", 8080, "us@r", "p:ss")
    assert proxy.url == "http://us%40r:p%3Ass@host:8080"
    assert proxy.for_requests() == {"http": proxy.url, "https": proxy.url}
    assert proxy.for_playwright() == {
        "server": "http://host:8080",
        "username": "us@r",
        "password": "p:ss",
    }
    assert str(proxy) == "http://host:8080"


def test_parse_proxy_list_skips_comments_and_collects_errors():
    proxies, errors = parse_proxy_list(["# comment", "", "a:1", "broken", "b:2"])
    assert [p.host for p in proxies] == ["a", "b"]
    assert len(errors) == 1


def test_round_robin_rotation():
    pool = ProxyPool([parse_proxy("a:1"), parse_proxy("b:2")])
    assert [pool.next().host for _ in range(4)] == ["a", "b", "a", "b"]


def test_random_rotation_and_empty_pool():
    pool = ProxyPool([parse_proxy("a:1")], mode="random")
    assert pool.next().host == "a"
    assert ProxyPool([]).next() is None
    with pytest.raises(ValueError):
        ProxyPool([], mode="nope")
