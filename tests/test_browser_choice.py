from sieve.core.browser import CHROME, EDGE, BrowserChoice, browser_from_command, launch_order


def test_chrome_and_edge_use_channels():
    chrome = browser_from_command(
        r'"C:\Program Files\Google\Chrome\Application\chrome.exe" --single-argument %1'
    )
    assert chrome == CHROME
    edge = browser_from_command(r'"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe" -- "%1"')
    assert edge == EDGE


def test_other_chromium_browsers_launch_their_executable():
    path = r"C:\Users\me\AppData\Local\BraveSoftware\Brave-Browser\Application\brave.exe"
    brave = browser_from_command(f'"{path}" --single-argument %1')
    assert brave == BrowserChoice("Brave", executable=path)
    assert brave.supported


def test_unsupported_browsers_are_named():
    firefox = browser_from_command(r'"C:\Program Files\Mozilla Firefox\firefox.exe" -osint -url "%1"')
    assert firefox.name == "Firefox" and not firefox.supported
    assert browser_from_command("") is None


def test_launch_order_prefers_default_then_falls_back():
    assert launch_order(None) == [CHROME, EDGE]
    assert launch_order(EDGE) == [EDGE, CHROME]
    assert launch_order(CHROME) == [CHROME, EDGE]
    brave = BrowserChoice("Brave", executable="brave.exe")
    assert launch_order(brave) == [brave, CHROME, EDGE]
    assert launch_order(BrowserChoice("Firefox")) == [CHROME, EDGE]
