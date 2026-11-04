"""Passing text from one tool to another ("Send to").

The main window installs a router at start-up; tool pages only call
``send_text`` and implement ``receive_text(text)``.
"""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtWidgets import QApplication, QMenu, QPushButton, QWidget

from sieve.ui.icons import icon

# (tool id, name, icon) for every tool, set by the main window.
_targets: list[tuple[str, str, str]] = []
_router: Callable[[str, str], None] | None = None


def install(targets: list[tuple[str, str, str]], router: Callable[[str, str], None]) -> None:
    global _router
    _targets[:] = targets
    _router = router


def send_text(tool_id: str, text: str) -> None:
    if _router is not None:
        _router(tool_id, text)


class SendToButton(QPushButton):
    """A compact "Send to" button listing every other tool."""

    def __init__(self, own_tool_id: str, get_text: Callable[[], str], parent: QWidget | None = None):
        super().__init__("Send to", parent)
        self.setProperty("compact", True)
        self.setToolTip("Use this result as the input of another tool.")
        self._own = own_tool_id
        self._get_text = get_text
        menu = QMenu(self)
        menu.aboutToShow.connect(lambda: self._fill(menu))
        self.setMenu(menu)

    def _fill(self, menu: QMenu) -> None:
        menu.clear()
        for tool_id, name, icon_name in _targets:
            if tool_id == self._own:
                continue
            action = menu.addAction(icon(icon_name), name)
            action.triggered.connect(lambda _=False, target=tool_id: self._send(target))

    def _send(self, tool_id: str) -> None:
        text = self._get_text()
        if text:
            send_text(tool_id, text)


def notify_finished(widget: QWidget) -> None:
    """Flash the taskbar button if the window is in the background."""
    window = widget.window()
    if window is not None and not window.isActiveWindow():
        QApplication.alert(window, 0)
