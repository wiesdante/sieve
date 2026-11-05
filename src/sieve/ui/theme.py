"""Terminal theme: black screen, phosphor green, one monospaced font everywhere.

``apply_theme`` loads the bundled JetBrains Mono, sets a Fusion palette and the
stylesheet, and installs a small helper that gives buttons and tabs their terminal
lettering (primary buttons in capitals, the rest in lower case) and primary buttons
a soft glow.
"""

from __future__ import annotations

import logging

from PySide6.QtCore import QEvent, QObject
from PySide6.QtGui import QColor, QFont, QFontDatabase, QPalette
from PySide6.QtWidgets import QApplication, QGraphicsDropShadowEffect, QPushButton, QTabBar

from sieve import paths

log = logging.getLogger(__name__)

FONT_FAMILY = "JetBrains Mono"
FONT_FILES = ("JetBrainsMono-Regular.ttf", "JetBrainsMono-Medium.ttf", "JetBrainsMono-Bold.ttf")

BACKGROUND = "#030703"
SURFACE = "#030703"          # panels sit on the same black as the window
SURFACE_ALT = "#0a1a0a"      # hover, selected rows, tooltips
BORDER = "#1d6b1d"
BORDER_DIM = "#123f12"
TEXT = "#a6f5a3"
TEXT_BRIGHT = "#d4ffd1"
TEXT_MUTED = "#4f9a4d"
TEXT_FAINT = "#2c632b"
ACCENT = "#39ff14"
ACCENT_HOVER = "#7dff5f"
ACCENT_DARK = "#1a7a0a"
SUCCESS = "#39ff14"
WARNING = "#ffb000"
DANGER = "#ff4b4b"
INFO = "#4fd6ff"
#: Translucent green for selections, so text stays readable.
SELECTION = "rgba(57, 255, 20, 0.28)"

STYLESHEET = f"""
QWidget {{
    color: {TEXT};
    font-family: "{FONT_FAMILY}", "Cascadia Mono", Consolas, monospace;
    font-size: 9.5pt;
}}
QMainWindow, QDialog, QStackedWidget, QScrollArea > QWidget > QWidget {{
    background: {BACKGROUND};
}}
QToolTip {{
    background: {SURFACE_ALT};
    color: {TEXT_BRIGHT};
    border: 1px solid {BORDER};
    padding: 4px 6px;
}}

/* Sidebar */
#Sidebar {{
    background: {BACKGROUND};
    border-right: 1px solid {BORDER_DIM};
}}
#BrandName {{
    color: {ACCENT};
    font-size: 13pt;
    font-weight: 700;
}}
#BrandVersion, #Footer {{
    color: {TEXT_FAINT};
    font-size: 8pt;
}}
#NavList {{
    background: transparent;
    border: none;
    outline: none;
}}
#NavList::item {{
    color: {TEXT_MUTED};
    padding: 6px 14px;
    margin: 0;
    border: none;
}}
#NavList::item:hover {{
    color: {TEXT_BRIGHT};
    background: {SURFACE_ALT};
}}
#NavList::item:selected {{
    background: {ACCENT};
    color: {BACKGROUND};
    font-weight: 700;
}}
#NavList::item:disabled {{
    color: {TEXT_FAINT};
    font-size: 8pt;
    padding: 14px 14px 4px 14px;
}}
#NavList::item:disabled:hover {{
    background: transparent;
}}
#NavList[collapsed="true"]::item {{
    padding: 9px 12px;
    margin: 1px 10px;
}}
#SidebarToggle {{
    background: transparent;
    border: 1px solid transparent;
    padding: 0;
}}
#SidebarToggle:hover {{
    border-color: {BORDER};
}}

/* Pages */
#PageTitle {{
    font-size: 15pt;
    font-weight: 700;
    color: {ACCENT};
}}
#PageSubtitle {{
    color: {TEXT_MUTED};
}}
QLabel[class="muted"] {{
    color: {TEXT_MUTED};
}}
#Card:hover {{
    border-color: {ACCENT};
    background: {SURFACE_ALT};
}}
#Card QLabel {{
    background: transparent;
}}
#Card, QGroupBox {{
    background: {BACKGROUND};
    border: 1px solid {BORDER};
    border-radius: 0;
}}
QGroupBox {{
    margin-top: 12px;
    padding: 16px 14px 12px 14px;
    font-weight: 700;
}}
QGroupBox::title {{
    subcontrol-origin: margin;
    left: 10px;
    padding: 0 6px;
    color: {ACCENT};
    background: {BACKGROUND};
}}
#Banner {{
    background: rgba(255, 176, 0, 0.08);
    border: 1px solid rgba(255, 176, 0, 0.55);
    border-radius: 0;
}}
#Banner QLabel {{
    color: {WARNING};
}}
#EmptyState {{
    color: {TEXT_MUTED};
    font-size: 10pt;
}}

/* Inputs */
QLineEdit, QPlainTextEdit, QTextBrowser, QComboBox, QSpinBox {{
    background: {BACKGROUND};
    color: {TEXT_BRIGHT};
    border: 1px solid {BORDER_DIM};
    border-radius: 0;
    padding: 5px 8px;
    selection-background-color: {SELECTION};
    selection-color: {TEXT_BRIGHT};
}}
QLineEdit:focus, QPlainTextEdit:focus, QComboBox:focus, QSpinBox:focus {{
    border-color: {ACCENT};
}}
QComboBox {{
    color: {TEXT};
    padding-right: 24px;
}}
QComboBox:hover {{
    border-color: {BORDER};
    color: {TEXT_BRIGHT};
}}
QComboBox::drop-down {{
    border: none;
    width: 22px;
}}
QComboBox QAbstractItemView {{
    background: {BACKGROUND};
    color: {TEXT};
    border: 1px solid {BORDER};
    selection-background-color: {ACCENT};
    selection-color: {BACKGROUND};
    outline: none;
}}

/* Check boxes: [x] */
QCheckBox {{
    spacing: 8px;
}}
QCheckBox::indicator {{
    width: 11px;
    height: 11px;
    border: 1px solid {BORDER};
    background: {BACKGROUND};
}}
QCheckBox::indicator:hover {{
    border-color: {ACCENT};
}}
QCheckBox::indicator:checked {{
    background: {ACCENT};
    border-color: {ACCENT};
}}
QCheckBox:disabled {{
    color: {TEXT_FAINT};
}}
QCheckBox::indicator:disabled {{
    border-color: {BORDER_DIM};
    background: {BACKGROUND};
}}
QRadioButton::indicator {{
    width: 11px;
    height: 11px;
    border: 1px solid {BORDER};
    border-radius: 6px;
}}
QRadioButton::indicator:checked {{
    background: {ACCENT};
}}

/* Buttons */
QPushButton {{
    background: {BACKGROUND};
    color: {ACCENT};
    border: 1px solid {ACCENT_DARK};
    border-radius: 0;
    padding: 6px 14px;
}}
QPushButton:hover {{
    border-color: {ACCENT};
    color: {ACCENT_HOVER};
    background: {SURFACE_ALT};
}}
QPushButton:pressed {{
    background: {ACCENT_DARK};
}}
QPushButton:disabled {{
    color: {TEXT_FAINT};
    border-color: {BORDER_DIM};
    background: {BACKGROUND};
}}
QPushButton[primary="true"] {{
    background: {ACCENT};
    border-color: {ACCENT};
    color: {BACKGROUND};
    font-weight: 700;
}}
QPushButton[primary="true"]:hover {{
    background: {ACCENT_HOVER};
    border-color: {ACCENT_HOVER};
    color: {BACKGROUND};
}}
QPushButton[primary="true"]:pressed {{
    background: {ACCENT_DARK};
}}
QPushButton[primary="true"]:disabled {{
    background: {BACKGROUND};
    border-color: {BORDER_DIM};
    color: {TEXT_FAINT};
}}
QPushButton[compact="true"] {{
    padding: 4px 10px;
}}
QPushButton::menu-indicator {{
    subcontrol-position: right center;
    right: 6px;
}}

/* Tabs */
QTabWidget::pane {{
    border: 1px solid {BORDER_DIM};
    border-radius: 0;
    top: -1px;
    background: {BACKGROUND};
}}
QTabBar::tab {{
    background: transparent;
    color: {TEXT_FAINT};
    padding: 6px 14px;
    border: none;
    border-bottom: 2px solid transparent;
}}
QTabBar::tab:selected {{
    color: {ACCENT};
    border-bottom: 2px solid {ACCENT};
}}
QTabBar::tab:hover:!selected {{
    color: {TEXT};
}}

/* Tables and lists */
QListWidget#FileList::item {{
    padding: 4px 6px;
}}
QTableWidget, QListWidget#FileList, QListWidget {{
    background: {BACKGROUND};
    alternate-background-color: {BACKGROUND};
    border: 1px solid {BORDER_DIM};
    border-radius: 0;
    gridline-color: {BORDER_DIM};
    selection-background-color: {SELECTION};
    selection-color: {TEXT_BRIGHT};
    outline: none;
}}
QTableWidget::item {{
    border-bottom: 1px dashed {BORDER_DIM};
    padding: 2px 4px;
}}
QHeaderView::section {{
    background: {BACKGROUND};
    color: {TEXT_MUTED};
    border: none;
    border-bottom: 1px solid {BORDER};
    padding: 5px 8px;
    font-weight: 400;
}}
QTableCornerButton::section {{
    background: {BACKGROUND};
    border: none;
}}

/* Tool panels: drawn by TerminalPanel (border with the title set into it) */
#Panel {{
    background: {BACKGROUND};
    border: none;
}}
#Panel QLabel {{
    background: {BACKGROUND};
}}
#PanelTitle {{
    color: {ACCENT};
    font-weight: 700;
    padding: 0 6px;
}}
#Toolbar {{
    background: {BACKGROUND};
    border: 1px solid {BORDER_DIM};
    border-radius: 0;
}}
#Stats {{
    color: {TEXT_MUTED};
}}
QSplitter::handle {{
    background: transparent;
}}
QPlainTextEdit#Editor {{
    font-size: 9.5pt;
    color: {TEXT_BRIGHT};
}}

/* Segmented mode switch */
QPushButton[segment] {{
    background: {BACKGROUND};
    border: 1px solid {ACCENT_DARK};
    color: {TEXT_MUTED};
    padding: 5px 14px;
    border-radius: 0;
}}
QPushButton[segment="right"], QPushButton[segment="middle"] {{
    border-left: none;
}}
QPushButton[segment]:checked {{
    background: {ACCENT};
    border-color: {ACCENT};
    color: {BACKGROUND};
    font-weight: 700;
}}
QPushButton[segment]:hover:!checked {{
    color: {ACCENT};
}}

QProgressBar {{
    background: {BACKGROUND};
    border: 1px solid {BORDER};
    border-radius: 0;
    text-align: center;
    color: {TEXT_BRIGHT};
    font-weight: 700;
    height: 16px;
}}
QProgressBar::chunk {{
    background: rgba(57, 255, 20, 0.45);
    margin: 2px;
}}
QScrollArea {{
    background: transparent;
    border: none;
}}
QScrollBar:vertical {{
    background: transparent;
    width: 8px;
    margin: 0;
}}
QScrollBar::handle:vertical {{
    background: {BORDER};
    min-height: 30px;
}}
QScrollBar::handle:vertical:hover {{
    background: {ACCENT_DARK};
}}
QScrollBar:horizontal {{
    background: transparent;
    height: 8px;
}}
QScrollBar::handle:horizontal {{
    background: {BORDER};
    min-width: 30px;
}}
QScrollBar::add-line, QScrollBar::sub-line, QScrollBar::add-page, QScrollBar::sub-page {{
    height: 0;
    width: 0;
    background: transparent;
}}
QMenu {{
    background: {BACKGROUND};
    border: 1px solid {BORDER};
    padding: 4px 0;
}}
QMenu::item {{
    padding: 5px 18px;
    color: {TEXT};
}}
QMenu::item:selected {{
    background: {ACCENT};
    color: {BACKGROUND};
}}
QMenu::separator {{
    height: 1px;
    background: {BORDER_DIM};
    margin: 4px 8px;
}}
QMessageBox QLabel {{
    color: {TEXT_BRIGHT};
}}
"""


def load_fonts() -> bool:
    """Register the bundled JetBrains Mono; False if the files are missing."""
    loaded = False
    for name in FONT_FILES:
        path = paths.resource_path("assets", "fonts", name)
        if path.exists() and QFontDatabase.addApplicationFont(str(path)) != -1:
            loaded = True
    if not loaded:
        log.warning("JetBrains Mono could not be loaded; using the system's monospaced font")
    return loaded


class _TerminalLettering(QObject):
    """Primary buttons in capitals with a glow, other buttons and tabs in lower case.

    Done through the font (not the text), so labels changed later, such as
    "Stopping...", keep the style.
    """

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:  # noqa: N802 (Qt override)
        kind = event.type()
        if kind == QEvent.Type.Polish:
            if isinstance(watched, QPushButton):
                self._style_button(watched)
            elif isinstance(watched, QTabBar):
                font = watched.font()
                font.setCapitalization(QFont.Capitalization.AllLowercase)
                watched.setFont(font)
        elif kind == QEvent.Type.EnabledChange and isinstance(watched, QPushButton):
            effect = watched.graphicsEffect()
            if isinstance(effect, QGraphicsDropShadowEffect):
                effect.setEnabled(watched.isEnabled())
        return False

    @staticmethod
    def _style_button(button: QPushButton) -> None:
        if button.objectName() == "SidebarToggle":
            return
        primary = bool(button.property("primary"))
        segment = button.property("segment") is not None
        font = button.font()
        font.setCapitalization(
            QFont.Capitalization.AllUppercase if primary or segment else QFont.Capitalization.AllLowercase
        )
        button.setFont(font)
        if primary and button.graphicsEffect() is None:
            glow = QGraphicsDropShadowEffect(button)
            glow.setColor(QColor(57, 255, 20, 110))
            glow.setBlurRadius(18)
            glow.setOffset(0, 0)
            glow.setEnabled(button.isEnabled())
            button.setGraphicsEffect(glow)


_lettering: _TerminalLettering | None = None


def apply_theme(app: QApplication) -> None:
    global _lettering
    app.setStyle("Fusion")
    if load_fonts():
        font = QFont(FONT_FAMILY)
        font.setPointSizeF(9.5)
        font.setStyleHint(QFont.StyleHint.Monospace)
        app.setFont(font)
    palette = QPalette()
    colors = {
        QPalette.ColorRole.Window: BACKGROUND,
        QPalette.ColorRole.WindowText: TEXT,
        QPalette.ColorRole.Base: BACKGROUND,
        QPalette.ColorRole.AlternateBase: BACKGROUND,
        QPalette.ColorRole.Text: TEXT_BRIGHT,
        QPalette.ColorRole.Button: BACKGROUND,
        QPalette.ColorRole.ButtonText: ACCENT,
        QPalette.ColorRole.Highlight: ACCENT,
        QPalette.ColorRole.HighlightedText: BACKGROUND,
        QPalette.ColorRole.Link: ACCENT,
        QPalette.ColorRole.LinkVisited: ACCENT_HOVER,
        QPalette.ColorRole.ToolTipBase: SURFACE_ALT,
        QPalette.ColorRole.ToolTipText: TEXT_BRIGHT,
        QPalette.ColorRole.PlaceholderText: TEXT_FAINT,
        QPalette.ColorRole.Mid: BORDER_DIM,
        QPalette.ColorRole.Dark: BACKGROUND,
        QPalette.ColorRole.Light: BORDER,
    }
    for role, color in colors.items():
        palette.setColor(role, QColor(color))
    for role in (QPalette.ColorRole.Text, QPalette.ColorRole.ButtonText, QPalette.ColorRole.WindowText):
        palette.setColor(QPalette.ColorGroup.Disabled, role, QColor(TEXT_FAINT))
    app.setPalette(palette)
    app.setStyleSheet(STYLESHEET)
    if _lettering is None:
        _lettering = _TerminalLettering(app)
        app.installEventFilter(_lettering)
