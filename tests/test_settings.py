import json

from sieve.settings import Settings, default_path


def test_defaults_when_missing():
    assert Settings.load() == Settings()


def test_round_trip():
    settings = Settings(proxy_enabled=True, proxies=["a:1", "b:2"], skipped_version="0.2.0")
    settings.save()
    assert Settings.load() == settings


def test_unknown_keys_and_wrong_types_are_ignored():
    default_path().write_text(
        json.dumps({"proxy_enabled": "yes", "proxies": ["a:1"], "future_option": 1}),
        encoding="utf-8",
    )
    loaded = Settings.load()
    assert loaded.proxy_enabled is False
    assert loaded.proxies == ["a:1"]


def test_corrupt_file_falls_back_to_defaults():
    default_path().write_text("{not json", encoding="utf-8")
    assert Settings.load() == Settings()
