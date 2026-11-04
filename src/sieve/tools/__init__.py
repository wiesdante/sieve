"""Registry of the tools available in the app.

To add a tool, create a module in this package with a ``Tool`` subclass and
append an instance to the list returned by ``all_tools``.
"""

from __future__ import annotations

from sieve.tools.base import Tool


def all_tools() -> list[Tool]:
    """Every tool shown in the sidebar, in display order."""
    from sieve.tools.duplicate_remover import DuplicateRemoverTool
    from sieve.tools.email_scraper import EmailScraperTool
    from sieve.tools.keyword_filter import KeywordFilterTool
    from sieve.tools.link_extractor import LinkExtractorTool
    from sieve.tools.text_stripper import TextStripperTool

    return [
        EmailScraperTool(),
        LinkExtractorTool(),
        DuplicateRemoverTool(),
        KeywordFilterTool(),
        TextStripperTool(),
    ]


__all__ = ["Tool", "all_tools"]
