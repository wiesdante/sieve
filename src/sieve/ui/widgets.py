"""Small reusable widgets and helpers."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QObject, Qt, QTimer, QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QAbstractItemView,
    QButtonGroup,
    QFrame,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QScrollArea,
    QSizePolicy,
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


def compact_button(text: str, tooltip: str = "") -> QPushButton:
    """Small secondary button for panel headers and footers."""
    button = QPushButton(text)
    button.setProperty("compact", True)
    button.setCursor(Qt.CursorShape.PointingHandCursor)
    if tooltip:
        button.setToolTip(tooltip)
    return button


def titled_panel(title: str) -> tuple[QFrame, QVBoxLayout, QHBoxLayout]:
    """A rounded panel with a header row; returns (panel, body layout, header layout)."""
    panel = QFrame()
    panel.setObjectName("Panel")
    body = QVBoxLayout(panel)
    body.setContentsMargins(14, 12, 14, 12)
    body.setSpacing(8)
    header = QHBoxLayout()
    header.setSpacing(6)
    label = QLabel(title)
    label.setObjectName("PanelTitle")
    header.addWidget(label)
    body.addLayout(header)
    return panel, body, header


def stats_html(items: list[tuple[str, int, str | None]]) -> str:
    """Inline statistics such as "Total 120 · Kept 80"; each item is (label, value, color)."""
    from sieve.ui import theme

    parts = []
    for label, value, color in items:
        style = f"color:{color or theme.TEXT}; font-weight:600"
        parts.append(f'{label} <span style="{style}">{format_number(value)}</span>')
    return "&nbsp;&nbsp;·&nbsp;&nbsp;".join(parts)


def flash_button(button: QPushButton, text: str, duration_ms: int = 1500) -> None:
    """Show a short confirmation on a button, then restore its label."""
    original = button.property("originalText") or button.text()
    button.setProperty("originalText", original)
    button.setText(text)
    QTimer.singleShot(duration_ms, lambda: button.setText(original))


class SegmentedControl(QObject):
    """Two or more mutually exclusive toggle buttons drawn as one control."""

    changed = Signal(str)

    def __init__(self, options: list[tuple[str, str, str]], parent: QWidget) -> None:
        """``options`` is a list of (key, label, tooltip)."""
        super().__init__(parent)
        self.layout = QHBoxLayout()
        self.layout.setSpacing(0)
        self._group = QButtonGroup(self)
        self._group.setExclusive(True)
        self._buttons: dict[str, QPushButton] = {}
        for index, (key, label, tooltip) in enumerate(options):
            button = QPushButton(label)
            button.setCheckable(True)
            position = "left" if index == 0 else "right" if index == len(options) - 1 else "middle"
            button.setProperty("segment", position)
            button.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.setToolTip(tooltip)
            button.clicked.connect(lambda _=False, k=key: self.changed.emit(k))
            self._group.addButton(button)
            self._buttons[key] = button
            self.layout.addWidget(button)

    def set_current(self, key: str) -> None:
        if key in self._buttons:
            self._buttons[key].setChecked(True)


class FileDropList(QListWidget):
    """A list of files that accepts drag and drop, filtered by extension."""

    files_added = Signal()

    def __init__(self, extensions: tuple[str, ...]) -> None:
        super().__init__()
        self.setObjectName("FileList")
        self._extensions = tuple(e.lower() for e in extensions)
        self.setAcceptDrops(True)
        self.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)

    def _accepted(self, event) -> list[Path]:
        if not event.mimeData().hasUrls():
            return []
        paths = [Path(url.toLocalFile()) for url in event.mimeData().urls() if url.isLocalFile()]
        return [p for p in paths if p.is_file() and p.suffix.lower() in self._extensions]

    def dragEnterEvent(self, event) -> None:  # noqa: N802 (Qt override)
        if self._accepted(event):
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragMoveEvent(self, event) -> None:  # noqa: N802 (Qt override)
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event) -> None:  # noqa: N802 (Qt override)
        files = self._accepted(event)
        if files:
            self.add_files(files)
            event.acceptProposedAction()

    def add_files(self, files: list[Path]) -> int:
        existing = set(self.paths())
        added = 0
        for path in files:
            if path in existing or path.suffix.lower() not in self._extensions:
                continue
            item = QListWidgetItem(path.name)
            item.setData(Qt.ItemDataRole.UserRole, str(path))
            item.setToolTip(str(path))
            self.addItem(item)
            existing.add(path)
            added += 1
        if added:
            self.files_added.emit()
        return added

    def remove_selected(self) -> None:
        for item in self.selectedItems():
            self.takeItem(self.row(item))

    def paths(self) -> list[Path]:
        return [Path(self.item(row).data(Qt.ItemDataRole.UserRole)) for row in range(self.count())]


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
