"""Small reusable widgets and helpers."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, QTimer, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QFrame,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)


def primary_button(text: str) -> QPushButton:
    button = QPushButton(text)
    button.setProperty("primary", True)
    button.setCursor(Qt.CursorShape.PointingHandCursor)
    return button


def muted_label(text: str = "", wrap: bool = True) -> QLabel:
    label = QLabel(text)
    label.setProperty("class", "muted")
    label.setWordWrap(wrap)
    return label


def open_folder(path: Path) -> None:
    QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))


def open_url(url: str) -> None:
    QDesktopServices.openUrl(QUrl(url))


def flash_button(button: QPushButton, text: str, duration_ms: int = 1500) -> None:
    """Show a short confirmation on a button, then restore its label."""
    original = button.property("originalText") or button.text()
    button.setProperty("originalText", original)
    button.setText(text)
    QTimer.singleShot(duration_ms, lambda: button.setText(original))


class ToolPage(QWidget):
    """Non-scrolling page for tools: a compact header and a layout that fills the window."""

    def __init__(self, title: str, subtitle: str = "") -> None:
        super().__init__()
        self.content = QVBoxLayout(self)
        self.content.setContentsMargins(24, 20, 24, 20)
        self.content.setSpacing(12)
        heading = QLabel(title)
        heading.setObjectName("PageTitle")
        self.content.addWidget(heading)
        if subtitle:
            sub = QLabel(subtitle)
            sub.setObjectName("PageSubtitle")
            sub.setWordWrap(True)
            self.content.addWidget(sub)


def format_number(value: int) -> str:
    """12345 -> "12,345"."""
    return f"{value:,}"


class Page(QScrollArea):
    """Scrollable page with a title, subtitle and a content layout."""

    def __init__(self, title: str, subtitle: str = "") -> None:
        super().__init__()
        self.setWidgetResizable(True)
        self.setFrameShape(QFrame.Shape.NoFrame)

        container = QWidget()
        self.content = QVBoxLayout(container)
        self.content.setContentsMargins(32, 28, 32, 28)
        self.content.setSpacing(14)

        heading = QLabel(title)
        heading.setObjectName("PageTitle")
        self.content.addWidget(heading)
        if subtitle:
            sub = QLabel(subtitle)
            sub.setObjectName("PageSubtitle")
            sub.setWordWrap(True)
            self.content.addWidget(sub)
        self.content.addSpacing(6)
        self.setWidget(container)

    def finish(self) -> None:
        """Call after adding content so it stays pinned to the top."""
        self.content.addStretch(1)
