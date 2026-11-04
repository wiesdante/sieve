from sieve.core.presets import DEFAULT_NAME, PresetLists


def test_old_plain_text_becomes_default_list():
    presets = PresetLists.from_data("spam\nads")
    assert presets.current == DEFAULT_NAME
    assert presets.text == "spam\nads"


def test_round_trip_and_bad_data():
    presets = PresetLists({"A": "1", "B": "2"}, "B")
    restored = PresetLists.from_data(presets.to_data())
    assert restored.lists == {"A": "1", "B": "2"} and restored.current == "B"
    assert PresetLists.from_data(None).lists == {DEFAULT_NAME: ""}
    assert PresetLists.from_data({"lists": {"A": 5}}).lists == {DEFAULT_NAME: ""}
    assert PresetLists.from_data({"lists": {"A": "x"}, "current": "missing"}).current == "A"


def test_unique_name():
    presets = PresetLists({"List": "", "List 2": ""})
    assert presets.unique_name("List") == "List 3"
