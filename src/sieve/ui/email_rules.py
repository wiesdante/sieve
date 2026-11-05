"""Settings for the email junk filter, shared by every tool that cleans addresses.

Saved in ``%APPDATA%\\Sieve\\data\\email_filter_settings.json``.
"""

from __future__ import annotations

import logging

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from sieve.core.email_filter import CATEGORIES, EmailFilter, FilterSettings, parse_entries
from sieve.storage import JsonDocument
from sieve.ui import theme
from sieve.ui.widgets import muted_label, primary_button

log = logging.getLogger(__name__)

DOCUMENT = "email_filter_settings"
ENTRY_HELP = (
    "One entry per line:\n"
    "  name@site.com   one address\n"
    "  site.com        a domain and all its subdomains\n"
    "  name@           a username at any domain"
)


def load_settings() -> FilterSettings:
    data = JsonDocument(DOCUMENT).load()
    return FilterSettings.from_dict(data) if data else FilterSettings()


def save_settings(settings: FilterSettings) -> None:
    JsonDocument(DOCUMENT).save(settings.to_dict())


def load_filter() -> EmailFilter:
    return EmailFilter(load_settings())


class EmailRulesDialog(QDialog):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Email filter")
        self.resize(680, 600)
        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        tabs = QTabWidget()
        tabs.addTab(self._build_checks_tab(), "Checks")
        tabs.addTab(self._build_list_tab("blocked"), "Block list")
        tabs.addTab(self._build_list_tab("allowed"), "Allow list")
        layout.addWidget(tabs, 1)

        buttons = QHBoxLayout()
        reset = QPushButton("Reset")
        reset.setToolTip("Turn every check back on and empty both lists.")
        reset.clicked.connect(self._reset)
        cancel = QPushButton("Cancel")
        cancel.clicked.connect(self.reject)
        save = primary_button("Save")
        save.clicked.connect(self._save)
        buttons.addWidget(reset)
        buttons.addStretch(1)
        buttons.addWidget(cancel)
        buttons.addWidget(save)
        layout.addLayout(buttons)

        self._show(load_settings())

    # ------------------------------------------------------------------ tabs
    def _build_checks_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(10)
        layout.addWidget(muted_label(
            "Every address first has to be a real address with a real domain ending, so "
            "file names like logo@2x.png are always removed. The checks below then decide "
            "what counts as junk. Removed addresses are listed with the reason, so you can "
            "spot mistakes and add exceptions to the Allow list."
        ))

        grid = QGridLayout()
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(8)
        self._category_boxes: dict[str, QCheckBox] = {}
        for row, (key, (title, description)) in enumerate(CATEGORIES.items()):
            box = QCheckBox(title)
            box.setStyleSheet("font-weight: 600;")
            self._category_boxes[key] = box
            grid.addWidget(box, row, 0, Qt.AlignmentFlag.AlignTop)
            grid.addWidget(muted_label(description), row, 1)
        grid.setColumnStretch(1, 1)
        layout.addLayout(grid)

        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setStyleSheet(f"color: {theme.BORDER_DIM};")
        layout.addWidget(line)

        self._mx = QCheckBox("Verify that the domain accepts email (MX check)")
        self._mx.setStyleSheet("font-weight: 600;")
        layout.addWidget(self._mx)
        layout.addWidget(muted_label(
            "Asks DNS whether each domain exists and has a mail server. Catches made-up and "
            "misspelled domains. Each domain is checked once per run, usually in well under a "
            "second; if DNS does not answer, the address is kept. DNS lookups use your own "
            "connection, not the proxies."
        ))
        layout.addStretch(1)
        return page

    def _build_list_tab(self, name: str) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(14, 12, 14, 12)
        intro = (
            "Addresses that match are always removed."
            if name == "blocked"
            else "Addresses that match are always kept, even if a check above would remove them."
        )
        layout.addWidget(muted_label(intro))
        help_label = QLabel(ENTRY_HELP)
        help_label.setObjectName("Stats")
        help_label.setStyleSheet(f"color: {theme.TEXT_MUTED};")
        layout.addWidget(help_label)
        editor = QPlainTextEdit()
        editor.setObjectName("Editor")
        editor.setPlaceholderText("agency-footer.com\nsales@competitor.com\ntest@")
        layout.addWidget(editor, 1)
        setattr(self, f"_{name}_editor", editor)
        return page

    # ----------------------------------------------------------------- state
    def _show(self, settings: FilterSettings) -> None:
        for key, box in self._category_boxes.items():
            box.setChecked(settings.categories.get(key, True))
        self._mx.setChecked(settings.check_mx)
        self._blocked_editor.setPlainText("\n".join(settings.blocked))
        self._allowed_editor.setPlainText("\n".join(settings.allowed))

    def _current(self) -> FilterSettings:
        return FilterSettings(
            categories={key: box.isChecked() for key, box in self._category_boxes.items()},
            blocked=parse_entries(self._blocked_editor.toPlainText()),
            allowed=parse_entries(self._allowed_editor.toPlainText()),
            check_mx=self._mx.isChecked(),
        )

    def _reset(self) -> None:
        answer = QMessageBox.question(
            self, "Reset", "Turn every check back on and empty your block and allow lists?"
        )
        if answer == QMessageBox.StandardButton.Yes:
            self._show(FilterSettings())

    def _save(self) -> None:
        try:
            save_settings(self._current())
        except OSError as exc:
            log.exception("Could not save email filter settings")
            QMessageBox.critical(self, "Email filter", f"The settings could not be saved:\n{exc}")
            return
        self.accept()
