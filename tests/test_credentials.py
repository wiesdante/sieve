from sieve.credentials import GITHUB_TOKEN, CredentialStore


def test_set_get_delete():
    store = CredentialStore()
    assert store.get(GITHUB_TOKEN) is None
    store.set(GITHUB_TOKEN, "github_pat_example")
    assert CredentialStore().get(GITHUB_TOKEN) == "github_pat_example"
    store.delete(GITHUB_TOKEN)
    assert store.get(GITHUB_TOKEN) is None


def test_value_is_not_stored_in_plain_text(isolated_home):
    CredentialStore().set("secret", "plain-value")
    raw = (isolated_home / "credentials.json").read_text(encoding="utf-8")
    assert "plain-value" not in raw
