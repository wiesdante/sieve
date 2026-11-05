"""Home page: token reminder and an overview of the available tools."""

from __future__ import annotations

from itertools import groupby

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QFrame, QGridLayout, QHBoxLayout, QLabel, QVBoxLayout

from sieve.context import AppContext
from sieve.credentials import GITHUB_TOKEN
from sieve.tools import Tool
from sieve.ui import theme
from sieve.ui.widgets import Page, command_name, muted_label, primary_button


class ToolCard(QFrame):
    clicked = Signal(str)

    def __init__(self, tool: Tool, number: int = 0) -> None:
        super().__init__()
        self.setObjectName("Card")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._tool_id = tool.id
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 14)
        name = QLabel(
            f'<span style="color:{theme.TEXT_FAINT}">{number:02d}</span>&nbsp;&nbsp;'
            f'<span style="color:{theme.ACCENT}; font-weight:700">{command_name(tool.name)}</span>'
        )
        name.setTextFormat(Qt.TextFormat.RichText)
        name.setStyleSheet("font-size: 10.5pt;")
        layout.addWidget(name)
        layout.addWidget(muted_label(tool.description))
        layout.addStretch(1)

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802 (Qt override)
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self._tool_id)
        super().mouseReleaseEvent(event)


class HomePage(Page):
    open_tool = Signal(str)
    open_settings = Signal()

    def __init__(self, context: AppContext, tools: list[Tool]) -> None:
        super().__init__("Home", "One place for all your data scraping workflows.")
        self._context = context

        self._banner = QFrame()
        self._banner.setObjectName("Banner")
        banner_layout = QHBoxLayout(self._banner)
        banner_layout.setContentsMargins(14, 10, 14, 10)
        banner_text = QLabel(
            "Add a GitHub token to enable automatic updates."
        )
        banner_text.setWordWrap(True)
        banner_button = primary_button("Open Settings")
        banner_button.clicked.connect(self.open_settings)
        banner_layout.addWidget(banner_text, 1)
        banner_layout.addWidget(banner_button)
        self.content.addWidget(self._banner)

        if not tools:
            empty = QLabel(
                "No tools yet.\nNew tools will appear here and in the sidebar."
            )
            empty.setObjectName("EmptyState")
            empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
            empty.setMinimumHeight(220)
            self.content.addWidget(empty)
        else:
            ordered = sorted(tools, key=lambda t: t.category)
            number = 0
            for category, group in groupby(ordered, key=lambda t: t.category):
                header = QLabel(f"# {category.lower()}")
                header.setStyleSheet(f"color: {theme.TEXT_MUTED}; margin-top: 8px;")
                self.content.addWidget(header)
                grid = QGridLayout()
                grid.setSpacing(12)
                for index, tool in enumerate(group):
                    number += 1
                    card = ToolCard(tool, number)
                    card.clicked.connect(self.open_tool)
                    grid.addWidget(card, index // 3, index % 3)
                for column in range(3):
                    grid.setColumnStretch(column, 1)
                self.content.addLayout(grid)

        self.finish()
        self.refresh()

    def refresh(self) -> None:
        self._banner.setVisible(not self._context.credentials.get(GITHUB_TOKEN))

    def showEvent(self, event) -> None:  # noqa: N802 (Qt override)
        self.refresh()
        super().showEvent(event)
