import pytest

from sieve.core.text_stripper import (
    PhraseStripper,
    StripCancelledError,
    StripOptions,
    parse_phrases,
    strip_lines,
)


def test_strips_labels_and_keeps_rest_of_line():
    lines = ["Email: john@example.com", "Phone: +90 555", "Name: Jane"]
    result = strip_lines(lines, ["Email: ", "Phone: "])
    assert result.lines == ["john@example.com", "+90 555", "Name: Jane"]
    assert result.total == 3
    assert result.changed == 2
    assert result.removals == 2


def test_trailing_space_in_phrase_is_significant():
    assert strip_lines(["Email: a@b.c"], ["Email:"]).lines == [" a@b.c"]
    assert strip_lines(["Email: a@b.c"], ["Email: "]).lines == ["a@b.c"]


def test_removes_every_occurrence_and_counts_them():
    result = strip_lines(["[ad] one [ad] two", "three"], ["[ad] "])
    assert result.lines == ["one two", "three"]
    assert result.phrase_hits == [("[ad] ", 2)]


def test_longest_phrase_wins_and_single_pass():
    lines = ["Email address: x@y.z"]
    assert strip_lines(lines, ["Email", "Email address: "]).lines == ["x@y.z"]
    # Removing "ab" must not join "a" + "b" into a new match.
    assert strip_lines(["aabb"], ["ab"]).lines == ["ab"]


def test_case_sensitive_by_default():
    assert strip_lines(["EMAIL: x"], ["Email: "]).lines == ["EMAIL: x"]


def test_ignore_case_counts_under_original_phrase():
    result = strip_lines(["EMAIL: x", "email: y", "İSTANBUL office"], ["Email: ", "istanbul "],
                         StripOptions(ignore_case=True))
    assert result.lines == ["x", "y", "office"]
    assert result.phrase_hits == [("Email: ", 2), ("istanbul ", 1)]


def test_trim_and_remove_empty():
    lines = ["  Price: 10  ", "Sponsored", "ok"]
    options = StripOptions(trim_lines=True, remove_empty=True)
    result = strip_lines(lines, ["Price:", "Sponsored"], options)
    assert result.lines == ["10", "ok"]
    assert result.dropped == 1


def test_unused_phrases_are_reported():
    result = strip_lines(["a"], ["a", "zzz"])
    assert result.phrase_hits == [("a", 1), ("zzz", 0)]


def test_special_characters_are_literal():
    assert strip_lines(["price (USD): $5.00"], ["(USD): $"]).lines == ["price 5.00"]


def test_parse_phrases_keeps_spaces_and_ignores_blank_lines():
    assert parse_phrases("Email: \r\n\n   \nEmail: \n Name") == ["Email: ", " Name"]


def test_empty_phrase_list_changes_nothing():
    assert strip_lines(["a", "b"], []).lines == ["a", "b"]
    assert PhraseStripper([]).strip("abc", {}) == "abc"


def test_cancel():
    with pytest.raises(StripCancelledError):
        strip_lines(["x"] * 50_000, ["x"], cancelled=lambda: True)
