"""Remove fixed phrases (labels, prefixes, boilerplate) from every line.

Typical use: turn scraped lines such as ``Email: john@example.com`` into
``john@example.com`` by stripping the phrase ``Email: ``.

Phrases are matched literally. Leading and trailing spaces in a phrase are
significant, so ``"Email: "`` also removes the space after the colon. All
phrases are applied in a single pass, longest first, so ``"Email address: "``
wins over ``"Email"`` and removing one phrase never creates a new match.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass, field

from sieve.core.keyword_filter import fold

_PROGRESS_EVERY = 20_000


class StripCancelledError(Exception):
    pass


@dataclass(frozen=True)
class StripOptions:
    ignore_case: bool = False
    #: Remove spaces left at the start and end of a line after stripping.
    trim_lines: bool = False
    #: Drop lines that are empty once the phrases have been removed.
    remove_empty: bool = False


@dataclass
class StripResult:
    lines: list[str]
    total: int
    #: Input lines in which at least one phrase was removed.
    changed: int
    #: Lines dropped because they became empty (only with ``remove_empty``).
    dropped: int
    #: (phrase, number of times it was removed), most frequent first; phrases
    #: that never matched are included with 0.
    phrase_hits: list[tuple[str, int]] = field(default_factory=list)

    @property
    def removals(self) -> int:
        return sum(count for _, count in self.phrase_hits)


def parse_phrases(text: str) -> list[str]:
    """One phrase per line, keeping leading/trailing spaces.

    Lines that are empty or contain only whitespace are ignored (they are almost
    always accidental and would otherwise delete every space). Repeats are
    ignored and the original order is kept.
    """
    seen: set[str] = set()
    phrases: list[str] = []
    for line in text.split("\n"):
        phrase = line.rstrip("\r")
        if phrase.strip() and phrase not in seen:
            seen.add(phrase)
            phrases.append(phrase)
    return phrases


class PhraseStripper:
    def __init__(self, phrases: list[str], ignore_case: bool = False) -> None:
        self._ignore_case = ignore_case
        self._by_key: dict[str, str] = {}
        for phrase in phrases:
            self._by_key.setdefault(self._key(phrase), phrase)
        if not self._by_key:
            self._pattern = None
            return
        ordered = sorted(self._by_key.values(), key=len, reverse=True)
        flags = re.IGNORECASE if ignore_case else 0
        self._pattern = re.compile("|".join(re.escape(p) for p in ordered), flags)

    def _key(self, text: str) -> str:
        return fold(text) if self._ignore_case else text

    def strip(self, line: str, hits: dict[str, int]) -> str:
        """Return ``line`` without the phrases, counting removals into ``hits``."""
        if self._pattern is None:
            return line

        def remove(match: re.Match[str]) -> str:
            phrase = self._by_key.get(self._key(match.group(0)))
            if phrase is not None:
                hits[phrase] = hits.get(phrase, 0) + 1
            return ""

        return self._pattern.sub(remove, line)


def strip_lines(
    lines: list[str],
    phrases: list[str],
    options: StripOptions | None = None,
    progress: Callable[[int, int], None] | None = None,
    cancelled: Callable[[], bool] | None = None,
) -> StripResult:
    options = options or StripOptions()
    stripper = PhraseStripper(phrases, options.ignore_case)
    hits: dict[str, int] = {phrase: 0 for phrase in phrases}
    output: list[str] = []
    changed = dropped = 0
    total = len(lines)

    for index, line in enumerate(lines, start=1):
        if index % _PROGRESS_EVERY == 0:
            if cancelled and cancelled():
                raise StripCancelledError
            if progress:
                progress(index, total)

        result = stripper.strip(line, hits)
        if result != line:
            changed += 1
        if options.trim_lines:
            result = result.strip()
        if options.remove_empty and not result.strip():
            dropped += 1
            continue
        output.append(result)

    if progress:
        progress(total, total)
    ranked = sorted(hits.items(), key=lambda item: (-item[1], fold(item[0])))
    return StripResult(output, total, changed, dropped, ranked)
