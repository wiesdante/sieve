"""The Link Collector's filter settings: built-in checks and saved exclude lists.

The checks live in the tool's settings; the exclude lists in
``%APPDATA%\\Sieve\\data\\link_exclude_lists.json``, so they survive updates.
"""

from __future__ import annotations

import logging

from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QHBoxLayout,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from sieve.core.link_collector import LinkFilterSettings, parse_rules
from sieve.core.presets import PresetLists
from sieve.storage import JsonDocument
from sieve.ui.presets import PresetBar
from sieve.ui.widgets import format_number, muted_label, primary_button

log = logging.getLogger(__name__)

EXCLUDE_DOCUMENT = "link_exclude_lists"
RULE_HELP = (
    "One rule per line. A link that contains the text is dropped (letter case is ignored), "
    "for example /login, wikipedia.org or ?sort=. Lines starting with # are notes."
)


def load_exclude_lists() -> PresetLists:
    return PresetLists.from_data(JsonDocument(EXCLUDE_DOCUMENT).load())


def save_exclude_lists(presets: PresetLists) -> None:
    JsonDocument(EXCLUDE_DOCUMENT).save(presets.to_data())


class LinkFiltersDialog(QDialog):
    """Edits the built-in checks (in ``prefs["filters"]``) and the exclude lists."""

    def __init__(self, prefs: dict, save_prefs, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Link filters")
        self.resize(620, 560)
        self._prefs = prefs
        self._save_prefs = save_prefs
        settings = LinkFilterSettings.from_dict(prefs.get("filters", {}))

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(10)

        self._social = QCheckBox("Skip social, share, app-store and map links")
        self._social.setToolTip("Facebook, X, LinkedIn, Instagram, YouTube, WhatsApp, share buttons, "
                                "App Store, Google Play, Google Maps and similar.")
        self._files = QCheckBox("Skip file downloads (PDF, images, documents, archives)")
        self._tracking = QCheckBox("Remove tracking parameters (utm_source, fbclid, gclid...)")
        self._tracking.setToolTip("Also makes the same page with different tracking count once.")
        for box, value in ((self._social, settings.skip_social), (self._files, settings.skip_files),
                           (self._tracking, settings.strip_tracking)):
            box.setChecked(value)
            box.setStyleSheet("font-weight: 600;")
            layout.addWidget(box)

        layout.addSpacing(6)
        title = QHBoxLayout()
        heading = muted_label("Exclude rules", wrap=False)
        heading.setStyleSheet("font-weight: 600;")
        title.addWidget(heading)
        self._count = muted_label(wrap=False)
        title.addWidget(self._count)
        title.addStretch(1)
        self._presets = load_exclude_lists()
        self._preset_bar = PresetBar("list")
        self._preset_bar.set_presets(self._presets)
        self._preset_bar.selected.connect(lambda _name: self._show_rules())
        title.addWidget(self._preset_bar)
        layout.addLayout(title)
        layout.addWidget(muted_label(RULE_HELP))

        self._rules = QPlainTextEdit()
        self._rules.setObjectName("Editor")
        self._rules.setPlaceholderText("/login\n/cart\nwikipedia.org")
        self._rules.textChanged.connect(self._on_rules_edited)
        layout.addWidget(self._rules, 1)
        self._show_rules()

        buttons = QHBoxLayout()
        cancel = QPushButton("Cancel")
        cancel.clicked.connect(self.reject)
        save = primary_button("Save")
        save.clicked.connect(self._save)
        buttons.addStretch(1)
        buttons.addWidget(cancel)
        buttons.addWidget(save)
        layout.addLayout(buttons)

    def _show_rules(self) -> None:
        self._rules.blockSignals(True)
        self._rules.setPlainText(self._presets.text)
        self._rules.blockSignals(False)
        self._update_count()

    def _on_rules_edited(self) -> None:
        self._presets.lists[self._presets.current] = self._rules.toPlainText()
        self._update_count()

    def _update_count(self) -> None:
        self._count.setText(f"· {format_number(len(parse_rules(self._rules.toPlainText())))} rules")

    def _save(self) -> None:
        filters = dict(self._prefs.get("filters", {}))
        filters.update(
            skip_social=self._social.isChecked(),
            skip_files=self._files.isChecked(),
            strip_tracking=self._tracking.isChecked(),
        )
        self._prefs["filters"] = filters
        self._save_prefs()
        try:
            save_exclude_lists(self._presets)
        except OSError:
            log.exception("Could not save the exclude lists")
        self.accept()
