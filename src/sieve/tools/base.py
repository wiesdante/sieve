"""Base class for the tools (modules) shown in the sidebar."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from PySide6.QtWidgets import QWidget

    from sieve.context import AppContext


class Tool(ABC):
    #: Stable identifier, used for settings keys. Never change it after release.
    id: str = ""
    #: Name shown in the sidebar.
    name: str = ""
    #: One-line description shown on the home page.
    description: str = ""
    #: Group heading on the home page.
    category: str = "General"
    #: Sidebar icon name from ``sieve.ui.icons.ICONS``.
    icon: str = "tool"

    @abstractmethod
    def create_widget(self, context: AppContext) -> QWidget:
        """Build the tool's page. Called once, the first time it is opened."""
