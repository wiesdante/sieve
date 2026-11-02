"""Registry of the tools available in the app.

To add a tool, create a module in this package with a ``Tool`` subclass and
append an instance to the list returned by ``all_tools``.
"""

from __future__ import annotations

from sieve.tools.base import Tool


def all_tools() -> list[Tool]:
    """Every tool shown in the sidebar, in display order."""
    from sieve.tools.duplicate_remover import DuplicateRemoverTool

    return [DuplicateRemoverTool()]


__all__ = ["Tool", "all_tools"]
