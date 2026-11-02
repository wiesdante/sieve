import pytest


@pytest.fixture(autouse=True)
def isolated_home(tmp_path, monkeypatch):
    """Keep every test away from the real settings and data folders."""
    monkeypatch.setenv("SIEVE_HOME", str(tmp_path / "home"))
    return tmp_path / "home"
