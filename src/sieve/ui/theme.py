"""Dark theme: Fusion palette plus a stylesheet for the custom widgets."""

from __future__ import annotations

from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QApplication

BACKGROUND = "#15161b"
SURFACE = "#1d1f26"
SURFACE_ALT = "#242731"
BORDER = "#2e3240"
TEXT = "#e7e9ef"
TEXT_MUTED = "#9096a8"
ACCENT = "#7c6cf2"
ACCENT_HOVER = "#8f81f5"
SUCCESS = "#3ecf8e"
WARNING = "#f2b84b"
DANGER = "#ef5f6b"

STYLESHEET = f"""
QWidget {{
    color: {TEXT};
    font-size: 10pt;
}}
QMainWindow, QDialog {{
    background: {BACKGROUND};
}}
QToolTip {{
    background: {SURFACE_ALT};
    color: {TEXT};
    border: 1px solid {BORDER};
    padding: 4px 6px;
}}

/* Sidebar */
#Sidebar {{
    background: {SURFACE};
    border-right: 1px solid {BORDER};
}}
#BrandName {{
    font-size: 16pt;
    font-weight: 600;
}}
#BrandVersion, #Footer {{
    color: {TEXT_MUTED};
    font-size: 9pt;
}}
#NavList {{
    background: transparent;
    border: none;
    outline: none;
}}
#NavList::item {{
    padding: 9px 12px;
    margin: 1px 8px;
    border-radius: 6px;
}}
#NavList::item:hover {{
    background: {SURFACE_ALT};
}}
#NavList::item:selected {{
    background: {ACCENT};
    color: white;
}}
#NavList::item:disabled {{
    color: {TEXT_MUTED};
    font-size: 8pt;
    font-weight: 600;
    padding: 14px 12px 4px 12px;
}}
#NavList::item:disabled:hover {{
    background: transparent;
}}
#NavSection {{
    color: {TEXT_MUTED};
    font-size: 8pt;
    font-weight: 600;
    padding: 12px 20px 4px 20px;
}}

/* Pages */
#PageTitle {{
    font-size: 18pt;
    font-weight: 600;
}}
#PageSubtitle, QLabel[class="muted"] {{
    color: {TEXT_MUTED};
}}
#Card, QGroupBox {{
    background: {SURFACE};
    border: 1px solid {BORDER};
    border-radius: 10px;
}}
QGroupBox {{
    margin-top: 14px;
    padding: 18px 14px 14px 14px;
    font-weight: 600;
}}
QGroupBox::title {{
    subcontrol-origin: margin;
    left: 12px;
    padding: 0 4px;
    color: {TEXT};
}}
#Banner {{
    background: rgba(242, 184, 75, 0.12);
    border: 1px solid rgba(242, 184, 75, 0.45);
    border-radius: 8px;
}}
#EmptyState {{
    color: {TEXT_MUTED};
    font-size: 11pt;
}}

/* Inputs */
QLineEdit, QPlainTextEdit, QTextBrowser, QComboBox, QSpinBox {{
    background: {BACKGROUND};
    border: 1px solid {BORDER};
    border-radius: 6px;
    padding: 6px 8px;
    selection-background-color: {ACCENT};
}}
QLineEdit:focus, QPlainTextEdit:focus, QComboBox:focus {{
    border-color: {ACCENT};
}}
QComboBox QAbstractItemView {{
    background: {SURFACE_ALT};
    border: 1px solid {BORDER};
    selection-background-color: {ACCENT};
}}

/* Buttons */
QPushButton {{
    background: {SURFACE_ALT};
    border: 1px solid {BORDER};
    border-radius: 6px;
    padding: 7px 14px;
}}
QPushButton:hover {{
    border-color: {ACCENT};
}}
QPushButton:pressed {{
    background: {BORDER};
}}
QPushButton:disabled {{
    color: {TEXT_MUTED};
    border-color: {SURFACE_ALT};
}}
QPushButton[primary="true"] {{
    background: {ACCENT};
    border-color: {ACCENT};
    color: white;
    font-weight: 600;
}}
QPushButton[primary="true"]:hover {{
    background: {ACCENT_HOVER};
}}
QPushButton[primary="true"]:disabled {{
    background: {SURFACE_ALT};
    border-color: {SURFACE_ALT};
    color: {TEXT_MUTED};
}}

/* Tabs */
QTabWidget::pane {{
    border: 1px solid {BORDER};
    border-radius: 8px;
    top: -1px;
    background: {SURFACE};
}}
QTabBar::tab {{
    background: transparent;
    color: {TEXT_MUTED};
    padding: 8px 16px;
    border-bottom: 2px solid transparent;
}}
QTabBar::tab:selected {{
    color: {TEXT};
    border-bottom: 2px solid {ACCENT};
}}
QTabBar::tab:hover {{
    color: {TEXT};
}}

/* Tables and lists */
QTableWidget, QListWidget#FileList {{
    background: {BACKGROUND};
    border: 1px solid {BORDER};
    border-radius: 6px;
    gridline-color: {BORDER};
    selection-background-color: {ACCENT};
}}
QHeaderView::section {{
    background: {SURFACE_ALT};
    color: {TEXT_MUTED};
    border: none;
    border-bottom: 1px solid {BORDER};
    padding: 6px 8px;
    font-weight: 600;
}}

/* Tool panels */
#Panel {{
    background: {SURFACE};
    border: 1px solid {BORDER};
    border-radius: 10px;
}}
#PanelTitle {{
    font-size: 11pt;
    font-weight: 600;
}}
#Toolbar {{
    background: {SURFACE};
    border: 1px solid {BORDER};
    border-radius: 10px;
}}
#Stats {{
    color: {TEXT_MUTED};
}}
QSplitter::handle {{
    background: transparent;
}}
QPlainTextEdit#Editor {{
    font-family: "Cascadia Mono", "Consolas", monospace;
    font-size: 10pt;
}}
QPushButton[compact="true"] {{
    background: {SURFACE_ALT};
    border: 1px solid {BORDER};
    border-radius: 6px;
    color: {TEXT};
    padding: 5px 10px;
}}
QPushButton[compact="true"]:hover {{
    border-color: {ACCENT};
    background: {BORDER};
}}
QPushButton[compact="true"]:pressed {{
    background: {BACKGROUND};
}}
QPushButton[compact="true"]:disabled {{
    background: transparent;
    border-color: {SURFACE_ALT};
    color: {TEXT_MUTED};
}}

/* Segmented mode switch */
QPushButton[segment] {{
    background: {BACKGROUND};
    border: 1px solid {BORDER};
    color: {TEXT_MUTED};
    padding: 6px 16px;
    border-radius: 0;
}}
QPushButton[segment="blacklist"] {{
    border-top-left-radius: 6px;
    border-bottom-left-radius: 6px;
}}
QPushButton[segment="whitelist"] {{
    border-top-right-radius: 6px;
    border-bottom-right-radius: 6px;
    border-left: none;
}}
QPushButton[segment]:checked {{
    background: {ACCENT};
    border-color: {ACCENT};
    color: white;
    font-weight: 600;
}}
QPushButton[segment]:hover:!checked {{
    color: {TEXT};
}}

QProgressBar {{
    background: {BACKGROUND};
    border: 1px solid {BORDER};
    border-radius: 6px;
    text-align: center;
    height: 18px;
}}
QProgressBar::chunk {{
    background: {ACCENT};
    border-radius: 5px;
}}
QScrollArea {{
    background: transparent;
    border: none;
}}
QScrollBar:vertical {{
    background: transparent;
    width: 10px;
}}
QScrollBar::handle:vertical {{
    background: {BORDER};
    border-radius: 5px;
    min-height: 30px;
}}
QScrollBar::add-line, QScrollBar::sub-line {{
    height: 0;
}}
"""


def apply_theme(app: QApplication) -> None:
    app.setStyle("Fusion")
    palette = QPalette()
    colors = {
        QPalette.ColorRole.Window: BACKGROUND,
        QPalette.ColorRole.WindowText: TEXT,
        QPalette.ColorRole.Base: BACKGROUND,
        QPalette.ColorRole.AlternateBase: SURFACE,
        QPalette.ColorRole.Text: TEXT,
        QPalette.ColorRole.Button: SURFACE_ALT,
        QPalette.ColorRole.ButtonText: TEXT,
        QPalette.ColorRole.Highlight: ACCENT,
        QPalette.ColorRole.HighlightedText: "#ffffff",
        QPalette.ColorRole.Link: ACCENT_HOVER,
        QPalette.ColorRole.ToolTipBase: SURFACE_ALT,
        QPalette.ColorRole.ToolTipText: TEXT,
        QPalette.ColorRole.PlaceholderText: TEXT_MUTED,
    }
    for role, color in colors.items():
        palette.setColor(role, QColor(color))
    palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Text, QColor(TEXT_MUTED))
    palette.setColor(
        QPalette.ColorGroup.Disabled, QPalette.ColorRole.ButtonText, QColor(TEXT_MUTED)
    )
    app.setPalette(palette)
    app.setStyleSheet(STYLESHEET)
