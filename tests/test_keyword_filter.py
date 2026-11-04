import pytest

from sieve.core.keyword_filter import (
    BLACKLIST,
    WHITELIST,
    FilterCancelledError,
    FilterOptions,
    KeywordMatcher,
    filter_lines,
    parse_keywords,
)

LINES = [
    "Buy cheap shoes",
    "Category: books",
    "Fresh apples for sale",
    "",
    "CAT food discount",
    "İstanbul office",
]


def test_blacklist_removes_matching_lines():
    result = filter_lines(LINES, ["cat", "shoes"], FilterOptions(mode=BLACKLIST))
    assert result.kept == ["Fresh apples for sale", "", "İstanbul office"]
    assert result.removed == ["Buy cheap shoes", "Category: books", "CAT food discount"]
    assert result.total == 6


def test_whitelist_keeps_only_matching_lines():
    result = filter_lines(LINES, ["cat", "apple"], FilterOptions(mode=WHITELIST))
    assert result.kept == ["Category: books", "Fresh apples for sale", "CAT food discount"]
    assert "" in result.removed


def test_whole_word():
    options = FilterOptions(mode=WHITELIST, whole_word=True)
    result = filter_lines(LINES, ["cat"], options)
    assert result.kept == ["CAT food discount"]


def test_case_sensitive():
    options = FilterOptions(mode=WHITELIST, ignore_case=False)
    assert filter_lines(LINES, ["CAT"], options).kept == ["CAT food discount"]


def test_turkish_dotted_i():
    result = filter_lines(LINES, ["istanbul"], FilterOptions(mode=WHITELIST))
    assert result.kept == ["İstanbul office"]


def test_skip_empty_lines_in_blacklist():
    result = filter_lines(LINES, ["cat"], FilterOptions(skip_empty=True))
    assert "" not in result.kept


def test_keyword_hits_include_unused_keywords():
    result = filter_lines(LINES, ["cat", "shoes", "unused"], FilterOptions())
    assert result.keyword_hits == [("cat", 2), ("shoes", 1), ("unused", 0)]


def test_empty_keyword_list():
    assert filter_lines(LINES, [], FilterOptions(mode=BLACKLIST)).kept == LINES
    assert filter_lines(LINES, [], FilterOptions(mode=WHITELIST)).kept == []


def test_special_characters_are_literal():
    result = filter_lines(["price $5 (sale)", "price 5 sale"], ["$5 (sale)"], FilterOptions())
    assert result.kept == ["price 5 sale"]


def test_matcher_reports_original_spelling_and_prefers_longest():
    matcher = KeywordMatcher(["New", "New York"])
    assert matcher.matches("I love NEW YORK") == {"New York"}
    assert not KeywordMatcher([])


def test_parse_keywords():
    assert parse_keywords("  cat \n\n#tag\ncat\nDog\n") == ["cat", "#tag", "Dog"]


def test_retention():
    result = filter_lines(["a", "b", "c", "d"], ["a"], FilterOptions())
    assert result.retention == 75.0


def test_invalid_mode():
    with pytest.raises(ValueError):
        FilterOptions(mode="greylist")


def test_cancel():
    with pytest.raises(FilterCancelledError):
        filter_lines(["x"] * 50_000, ["x"], cancelled=lambda: True)


# ------------------------------------------------------------------- regex
def test_regex_mode():
    from sieve.core.keyword_filter import PatternError

    lines = ["Order #12345 shipped", "Call 0212 555 55 55", "Hello world", "İstanbul ofisi"]
    options = FilterOptions(mode=WHITELIST, regex=True)
    result = filter_lines(lines, [r"#\d{5}", r"\d{4} \d{3}", "istanbul"], options)
    assert result.kept == ["Order #12345 shipped", "Call 0212 555 55 55", "İstanbul ofisi"]
    assert dict(result.keyword_hits)[r"#\d{5}"] == 1

    with pytest.raises(PatternError) as info:
        filter_lines(lines, ["(unclosed"], options)
    assert info.value.errors[0][0] == "(unclosed"


def test_regex_whole_word():
    options = FilterOptions(mode=WHITELIST, regex=True, whole_word=True)
    assert filter_lines(["cat", "category"], ["ca."], options).kept == ["cat"]
