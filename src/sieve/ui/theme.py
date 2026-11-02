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

/* Stat tiles */
#StatTile {{
    background: {BACKGROUND};
    border: 1px solid {BORDER};
    border-radius: 8px;
}}
#StatValue {{
    font-size: 16pt;
    font-weight: 600;
}}
#StatLabel {{
    color: {TEXT_MUTED};
    font-size: 9pt;
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
