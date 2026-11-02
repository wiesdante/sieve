import pytest

from sieve.storage import JsonDocument


def test_round_trip_survives_new_instances():
    JsonDocument("keyword_lists").save({"blacklist": "spam\nads", "whitelist": "İstanbul"})
    assert JsonDocument("keyword_lists").load() == {"blacklist": "spam\nads", "whitelist": "İstanbul"}


def test_missing_document_returns_default():
    assert JsonDocument("nothing").load({"a": 1}) == {"a": 1}


def test_corrupt_file_falls_back_to_backup():
    doc = JsonDocument("lists")
    doc.save({"v": 1})
    doc.save({"v": 2})
    doc.path.write_text("{broken", encoding="utf-8")
    assert JsonDocument("lists").load() == {"v": 1}


def test_lives_in_settings_folder_not_install_folder(isolated_home):
    doc = JsonDocument("lists")
    doc.save({})
    assert doc.path.is_relative_to(isolated_home)


def test_rejects_unsafe_names():
    with pytest.raises(ValueError):
        JsonDocument("../evil")
