"""Website Finder rules: which kinds of sites never count as a company's website,
and your own block lists.

The category switches live in the tool's settings; the block lists in
``%APPDATA%\\Sieve\\data\\website_block_lists.json``, so they survive updates.
"""

from __future__ import annotations

import logging

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QGridLayout,
    QHBoxLayout,
    QPlainTextEdit,
    QPushButton,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from sieve.core.presets import PresetLists
from sieve.core.website_finder import CATEGORIES, FinderSettings, parse_block_rules
from sieve.storage import JsonDocument
from sieve.ui.presets import PresetBar
from sieve.ui.widgets import format_number, muted_label, primary_button

log = logging.getLogger(__name__)

BLOCK_DOCUMENT = "website_block_lists"
BLOCK_HELP = (
    "One rule per line. A domain (firmabul.com) also covers its subdomains; any other text "
    "(/firma/, ?id=) blocks every address that contains it. Text after # is a note."
)


def load_block_lists() -> PresetLists:
    return PresetLists.from_data(JsonDocument(BLOCK_DOCUMENT).load())


def save_block_lists(presets: PresetLists) -> None:
    JsonDocument(BLOCK_DOCUMENT).save(presets.to_data())


class WebsiteRulesDialog(QDialog):
    """Edits ``prefs["rules"]`` (category switches) and the saved block lists."""

    def __init__(self, prefs: dict, save_prefs, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Website rules")
        self.resize(680, 600)
        self._prefs = prefs
        self._save_prefs = save_prefs
        settings = FinderSettings.from_dict(prefs.get("rules", {}))

        layout = QVBoxLayout(self)
        layout.setSpacing(10)
        tabs = QTabWidget()
        tabs.addTab(self._build_categories_tab(settings), "Never a company website")
        tabs.addTab(self._build_block_tab(), "Your block list")
        layout.addWidget(tabs, 1)

        buttons = QHBoxLayout()
        cancel = QPushButton("Cancel")
        cancel.clicked.connect(self.reject)
        save = primary_button("Save")
        save.clicked.connect(self._save)
        buttons.addStretch(1)
        buttons.addWidget(cancel)
        buttons.addWidget(save)
        layout.addLayout(buttons)

    def _build_categories_tab(self, settings: FinderSettings) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(10)
        layout.addWidget(muted_label(
            "Results on these sites are skipped, so a company's LinkedIn page or directory "
            "entry is never taken for its website. If the company is the platform itself "
            "(searching “Trendyol”), its site is still found."
        ))
        grid = QGridLayout()
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(8)
        self._boxes: dict[str, QCheckBox] = {}
        for row, (key, category) in enumerate(CATEGORIES.items()):
            box = QCheckBox(category.title)
            box.setStyleSheet("font-weight: 600;")
            box.setChecked(key in settings.categories)
            self._boxes[key] = box
            grid.addWidget(box, row, 0, Qt.AlignmentFlag.AlignTop)
            grid.addWidget(muted_label(category.description), row, 1)
        grid.setColumnStretch(1, 1)
        layout.addLayout(grid)
        layout.addStretch(1)
        return page

    def _build_block_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(14, 12, 14, 12)
        title = QHBoxLayout()
        self._count = muted_label(wrap=False)
        title.addWidget(self._count)
        title.addStretch(1)
        self._presets = load_block_lists()
        self._preset_bar = PresetBar("list")
        self._preset_bar.set_presets(self._presets)
        self._preset_bar.selected.connect(lambda _name: self._show_rules())
        title.addWidget(self._preset_bar)
        layout.addLayout(title)
        layout.addWidget(muted_label(BLOCK_HELP))
        self._rules = QPlainTextEdit()
        self._rules.setObjectName("Editor")
        self._rules.setPlaceholderText("firmabul.com\nbulurum.com\n/firma/")
        self._rules.textChanged.connect(self._on_rules_edited)
        layout.addWidget(self._rules, 1)
        self._show_rules()
        return page

    def _show_rules(self) -> None:
        self._rules.blockSignals(True)
        self._rules.setPlainText(self._presets.text)
        self._rules.blockSignals(False)
        self._update_count()

    def _on_rules_edited(self) -> None:
        self._presets.lists[self._presets.current] = self._rules.toPlainText()
        self._update_count()

    def _update_count(self) -> None:
        self._count.setText(f"{format_number(len(parse_block_rules(self._rules.toPlainText())))} rules")

    def _save(self) -> None:
        rules = dict(self._prefs.get("rules", {}))
        rules["categories"] = sorted(key for key, box in self._boxes.items() if box.isChecked())
        self._prefs["rules"] = rules
        self._save_prefs()
        try:
            save_block_lists(self._presets)
        except OSError:
            log.exception("Could not save the block lists")
        self.accept()
