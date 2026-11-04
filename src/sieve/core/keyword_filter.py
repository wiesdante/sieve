"""Keep or drop lines depending on whether they contain any keyword.

* **Blacklist** mode removes every line that contains at least one keyword.
* **Whitelist** mode keeps only the lines that contain at least one keyword.

Matching is a substring search by default ("cat" matches "category"); the
whole-word option requires the keyword to stand on its own.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass, field

BLACKLIST = "blacklist"
WHITELIST = "whitelist"
MODES = (BLACKLIST, WHITELIST)
_PROGRESS_EVERY = 20_000


class FilterCancelledError(Exception):
    pass


@dataclass(frozen=True)
class FilterOptions:
    mode: str = BLACKLIST
    ignore_case: bool = True
    whole_word: bool = False
    skip_empty: bool = False
    #: Keywords are regular expressions instead of plain text.
    regex: bool = False

    def __post_init__(self) -> None:
        if self.mode not in MODES:
            raise ValueError(f"Unknown mode: {self.mode}")


@dataclass
class FilterResult:
    kept: list[str]
    removed: list[str]
    total: int
    #: (keyword, number of lines containing it), most frequent first; keywords
    #: that matched nothing are included with 0 so dead entries are easy to spot.
    keyword_hits: list[tuple[str, int]] = field(default_factory=list)

    @property
    def retention(self) -> float:
        """Share of input lines that were kept, 0-100."""
        return 100.0 * len(self.kept) / self.total if self.total else 0.0


def fold(text: str) -> str:
    """Case-fold for comparison, mapping Turkish "İ" to a plain "i"."""
    return text.replace("İ", "i").casefold()


def parse_keywords(text: str) -> list[str]:
    """One keyword per line; blank lines and repeats are ignored, order is kept."""
    seen: set[str] = set()
    keywords: list[str] = []
    for line in text.splitlines():
        keyword = line.strip()
        if keyword and keyword not in seen:
            seen.add(keyword)
            keywords.append(keyword)
    return keywords


class PatternError(ValueError):
    """One or more regular expressions are invalid; ``errors`` lists (pattern, message)."""

    def __init__(self, errors: list[tuple[str, str]]) -> None:
        self.errors = errors
        super().__init__("; ".join(f"{pattern}: {message}" for pattern, message in errors))


def check_patterns(patterns: list[str]) -> list[tuple[str, str]]:
    """(pattern, error message) for every pattern that is not a valid regular expression."""
    errors = []
    for pattern in patterns:
        try:
            re.compile(pattern)
        except re.error as exc:
            errors.append((pattern, str(exc)))
    return errors


class RegexMatcher:
    """Like KeywordMatcher, but every keyword is a regular expression."""

    def __init__(self, patterns: list[str], ignore_case: bool = True, whole_word: bool = False):
        errors = check_patterns(patterns)
        if errors:
            raise PatternError(errors)
        self._ignore_case = ignore_case
        flags = re.IGNORECASE if ignore_case else 0
        self._compiled = [
            (pattern, re.compile(rf"(?<!\w)(?:{pattern})(?!\w)" if whole_word else pattern, flags))
            for pattern in dict.fromkeys(patterns)
        ]

    def __bool__(self) -> bool:
        return bool(self._compiled)

    def matches(self, line: str) -> set[str]:
        haystack = line.replace("İ", "i") if self._ignore_case else line
        return {pattern for pattern, compiled in self._compiled if compiled.search(haystack)}


class KeywordMatcher:
    """Finds which keywords occur in a line, using one compiled pattern."""

    def __init__(self, keywords: list[str], ignore_case: bool = True, whole_word: bool = False):
        self._ignore_case = ignore_case
        # Map the comparable form back to the keyword as the user wrote it.
        self._by_key: dict[str, str] = {}
        for keyword in keywords:
            key = fold(keyword) if ignore_case else keyword
            self._by_key.setdefault(key, keyword)

        if not self._by_key:
            self._pattern = None
            return
        # Longest first, so "new york" wins over "new" at the same position.
        alternatives = "|".join(
            re.escape(key) for key in sorted(self._by_key, key=len, reverse=True)
        )
        if whole_word:
            alternatives = rf"(?<!\w)(?:{alternatives})(?!\w)"
        self._pattern = re.compile(alternatives)

    def __bool__(self) -> bool:
        return self._pattern is not None

    def matches(self, line: str) -> set[str]:
        """The keywords found in ``line`` (as originally written)."""
        if self._pattern is None:
            return set()
        haystack = fold(line) if self._ignore_case else line
        return {self._by_key[m.group(0)] for m in self._pattern.finditer(haystack)}


def filter_lines(
    lines: list[str],
    keywords: list[str],
    options: FilterOptions | None = None,
    progress: Callable[[int, int], None] | None = None,
    cancelled: Callable[[], bool] | None = None,
) -> FilterResult:
    options = options or FilterOptions()
    matcher_type = RegexMatcher if options.regex else KeywordMatcher
    matcher = matcher_type(keywords, options.ignore_case, options.whole_word)
    hits: dict[str, int] = {keyword: 0 for keyword in keywords}
    kept: list[str] = []
    removed: list[str] = []
    total = len(lines)

    for index, line in enumerate(lines, start=1):
        if index % _PROGRESS_EVERY == 0:
            if cancelled and cancelled():
                raise FilterCancelledError
            if progress:
                progress(index, total)

        if not line.strip():
            if options.skip_empty:
                removed.append(line)
            elif options.mode == BLACKLIST:
                kept.append(line)
            else:
                removed.append(line)
            continue

        found = matcher.matches(line)
        for keyword in found:
            hits[keyword] = hits.get(keyword, 0) + 1
        keep = (not found) if options.mode == BLACKLIST else bool(found)
        (kept if keep else removed).append(line)

    if progress:
        progress(total, total)
    ranked = sorted(hits.items(), key=lambda item: (-item[1], fold(item[0])))
    return FilterResult(kept, removed, total, ranked)
