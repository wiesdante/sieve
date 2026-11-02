"""Duplicate line removal.

Lines are compared by a *key* built from the line according to the options
(trimmed, optionally case-folded and whitespace-collapsed). The first
occurrence of each key is kept, in its original position.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass, field

_WHITESPACE = re.compile(r"\s+")
_PROGRESS_EVERY = 50_000

SORT_MODES = {"none": "Orijinal sıra", "asc": "A → Z", "desc": "Z → A"}


class DedupeCancelledError(Exception):
    pass


@dataclass(frozen=True)
class DedupeOptions:
    ignore_case: bool = True
    collapse_whitespace: bool = True
    remove_empty: bool = True
    #: Write the normalised key instead of the original line (old script behaviour).
    output_normalized: bool = False
    sort: str = "none"

    def __post_init__(self) -> None:
        if self.sort not in SORT_MODES:
            raise ValueError(f"Unknown sort mode: {self.sort}")


@dataclass
class DedupeResult:
    #: Output lines, ready to be written.
    lines: list[str]
    #: Number of input lines.
    total: int
    #: Input lines that were empty (or whitespace only).
    empty: int
    #: Number of distinct non-empty lines.
    unique: int
    #: (first occurrence as written, number of times it appeared) for repeated lines.
    duplicates: list[tuple[str, int]] = field(default_factory=list)

    @property
    def removed(self) -> int:
        """How many lines were dropped as duplicates."""
        return sum(count - 1 for _, count in self.duplicates)


def normalize(line: str, options: DedupeOptions) -> str:
    key = line.strip()
    if options.collapse_whitespace:
        key = _WHITESPACE.sub(" ", key)
    if options.ignore_case:
        # str.lower() turns "İ" into "i̇" (i + combining dot); map it to a plain "i"
        # first so Turkish text compares the way people expect.
        key = key.replace("İ", "i").casefold()
    return key


def remove_duplicates(
    lines: list[str],
    options: DedupeOptions | None = None,
    progress: Callable[[int, int], None] | None = None,
    cancelled: Callable[[], bool] | None = None,
) -> DedupeResult:
    options = options or DedupeOptions()
    total = len(lines)
    kept: list[str] = []
    counts: dict[str, int] = {}
    first_seen: dict[str, str] = {}
    empty = 0
    empty_kept = 0

    for index, raw in enumerate(lines, start=1):
        if index % _PROGRESS_EVERY == 0:
            if cancelled and cancelled():
                raise DedupeCancelledError
            if progress:
                progress(index, total)

        key = normalize(raw, options)
        if not key:
            empty += 1
            if not options.remove_empty:
                kept.append("")
                empty_kept += 1
            continue

        if key in counts:
            counts[key] += 1
            continue
        counts[key] = 1
        written = key if options.output_normalized else raw.strip()
        first_seen[key] = written
        kept.append(written)

    if options.sort != "none":
        non_empty = [line for line in kept if line]
        non_empty.sort(key=lambda line: normalize(line, options), reverse=options.sort == "desc")
        kept = non_empty + [""] * empty_kept

    duplicates = sorted(
        ((first_seen[key], count) for key, count in counts.items() if count > 1),
        key=lambda item: (-item[1], item[0]),
    )
    if progress:
        progress(total, total)
    return DedupeResult(kept, total, empty, len(counts), duplicates)
