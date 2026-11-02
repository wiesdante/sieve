import pytest

from sieve.core.dedupe import (
    DedupeCancelledError,
    DedupeOptions,
    normalize,
    remove_duplicates,
)


def test_defaults_match_original_script_rules():
    lines = ["Apple", "apple ", "  APPLE", "", "   ", "Banana\tSplit", "banana  split", "Cherry"]
    result = remove_duplicates(lines)
    assert result.lines == ["Apple", "Banana\tSplit", "Cherry"]
    assert result.total == 8
    assert result.empty == 2
    assert result.unique == 3
    assert result.removed == 3
    assert result.duplicates == [("Apple", 3), ("Banana\tSplit", 2)]


def test_keeps_original_text_of_first_occurrence():
    result = remove_duplicates(["https://x.com/Path?A=1", "https://X.com/path?a=1"])
    assert result.lines == ["https://x.com/Path?A=1"]


def test_output_normalized_reproduces_old_behaviour():
    options = DedupeOptions(output_normalized=True)
    result = remove_duplicates(["  Foo   BAR ", "foo bar"], options)
    assert result.lines == ["foo bar"]


def test_case_sensitive_mode():
    result = remove_duplicates(["A", "a"], DedupeOptions(ignore_case=False))
    assert result.lines == ["A", "a"]


def test_whitespace_sensitive_mode():
    result = remove_duplicates(["a b", "a  b"], DedupeOptions(collapse_whitespace=False))
    assert result.lines == ["a b", "a  b"]


def test_keep_empty_lines():
    result = remove_duplicates(["a", "", "a", " ", "b"], DedupeOptions(remove_empty=False))
    assert result.lines == ["a", "", "", "b"]
    assert result.unique == 2


def test_turkish_dotted_capital_i():
    assert normalize("İSTANBUL", DedupeOptions()) == normalize("istanbul", DedupeOptions())
    assert remove_duplicates(["İzmir", "izmir"]).lines == ["İzmir"]


@pytest.mark.parametrize(("mode", "expected"), [("asc", ["a", "B", "c"]), ("desc", ["c", "B", "a"])])
def test_sorting(mode, expected):
    assert remove_duplicates(["c", "a", "B", "A"], DedupeOptions(sort=mode)).lines == expected


def test_invalid_sort_mode():
    with pytest.raises(ValueError):
        DedupeOptions(sort="random")


def test_progress_and_cancel():
    lines = [str(i % 1000) for i in range(120_000)]
    calls = []
    result = remove_duplicates(lines, progress=lambda done, total: calls.append((done, total)))
    assert result.unique == 1000
    assert calls[-1] == (120_000, 120_000)
    with pytest.raises(DedupeCancelledError):
        remove_duplicates(lines, cancelled=lambda: True)
