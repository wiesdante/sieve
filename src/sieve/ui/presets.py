"""Named, saved lists (e.g. several blacklists) with a picker and a small menu."""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QInputDialog,
    QMenu,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QWidget,
)

from sieve.core.presets import PresetLists


class PresetBar(QWidget):
    """Picker + "Lists" menu. Emits ``selected`` when another list is chosen and
    ``changed`` whenever the set of lists changes (add/rename/delete)."""

    selected = Signal(str)
    changed = Signal()

    def __init__(self, noun: str = "list", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._noun = noun
        self._presets = PresetLists()
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        self._combo = QComboBox()
        self._combo.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToContents)
        self._combo.setMinimumWidth(110)
        self._combo.setToolTip(f"Switch between your saved {noun}s.")
        self._combo.currentTextChanged.connect(self._on_pick)
        layout.addWidget(self._combo)

        self._menu_button = QPushButton("⋯")
        self._menu_button.setProperty("compact", True)
        self._menu_button.setFixedWidth(34)
        # The "⋯" already says "menu"; the default arrow would hide it in a narrow button.
        self._menu_button.setStyleSheet("QPushButton::menu-indicator { image: none; width: 0px; }")
        self._menu_button.setToolTip(f"New, rename, duplicate or delete {noun}s")
        menu = QMenu(self)
        menu.addAction(f"New {noun}...", self._new)
        menu.addAction("Rename...", self._rename)
        menu.addAction("Duplicate", self._duplicate)
        menu.addSeparator()
        self._delete_action = menu.addAction("Delete", self._delete)
        self._menu_button.setMenu(menu)
        layout.addWidget(self._menu_button)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)

    # ------------------------------------------------------------------ data
    @property
    def presets(self) -> PresetLists:
        return self._presets

    def set_presets(self, presets: PresetLists) -> None:
        self._presets = presets
        self._refresh()

    def set_current_text(self, text: str) -> None:
        """Store the editor's text for the selected list."""
        self._presets.lists[self._presets.current] = text

    def _refresh(self) -> None:
        self._combo.blockSignals(True)
        self._combo.clear()
        self._combo.addItems(list(self._presets.lists))
        self._combo.setCurrentText(self._presets.current)
        self._combo.blockSignals(False)
        self._delete_action.setEnabled(len(self._presets.lists) > 1)

    def _on_pick(self, name: str) -> None:
        if name and name in self._presets.lists and name != self._presets.current:
            self._presets.current = name
            self.selected.emit(name)
            self.changed.emit()

    def _select(self, name: str) -> None:
        self._presets.current = name
        self._refresh()
        self.selected.emit(name)
        self.changed.emit()

    # ----------------------------------------------------------------- menu
    def _ask_name(self, title: str, value: str) -> str | None:
        name, ok = QInputDialog.getText(self, title, f"Name of the {self._noun}:", text=value)
        name = name.strip()
        if not ok or not name:
            return None
        if name in self._presets.lists and name != self._presets.current:
            QMessageBox.information(self, title, f"There is already a {self._noun} called “{name}”.")
            return None
        return name

    def _new(self) -> None:
        name = self._ask_name(f"New {self._noun}", self._presets.unique_name(f"New {self._noun}"))
        if name:
            self._presets.lists[name] = ""
            self._select(name)

    def _rename(self) -> None:
        old = self._presets.current
        name = self._ask_name("Rename", old)
        if name and name != old:
            # Keep the order of the lists.
            self._presets.lists = {name if key == old else key: text for key, text in self._presets.lists.items()}
            self._presets.current = name
            self._refresh()
            self.changed.emit()

    def _duplicate(self) -> None:
        name = self._presets.unique_name(f"{self._presets.current} copy")
        self._presets.lists[name] = self._presets.text
        self._select(name)

    def _delete(self) -> None:
        if len(self._presets.lists) <= 1:
            return
        name = self._presets.current
        answer = QMessageBox.question(self, "Delete", f"Delete the {self._noun} “{name}”?")
        if answer != QMessageBox.StandardButton.Yes:
            return
        names = list(self._presets.lists)
        index = names.index(name)
        del self._presets.lists[name]
        remaining = list(self._presets.lists)
        self._select(remaining[min(index, len(remaining) - 1)])
