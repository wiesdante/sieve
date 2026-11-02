"""Small reusable widgets and helpers."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, QUrl
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


class StatTile(QFrame):
    """A small labelled number, e.g. "Unique  12.345"."""

    def __init__(self, label: str) -> None:
        super().__init__()
        self.setObjectName("StatTile")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 10, 14, 10)
        layout.setSpacing(2)
        self._value = QLabel("—")
        self._value.setObjectName("StatValue")
        caption = QLabel(label)
        caption.setObjectName("StatLabel")
        layout.addWidget(self._value)
        layout.addWidget(caption)

    def set_value(self, value: int | None, color: str | None = None) -> None:
        self._value.setText("—" if value is None else format_number(value))
        self._value.setStyleSheet(f"color: {color};" if color else "")


def format_number(value: int) -> str:
    """12345 -> "12.345" (Turkish thousands separator)."""
    return f"{value:,}".replace(",", ".")


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
