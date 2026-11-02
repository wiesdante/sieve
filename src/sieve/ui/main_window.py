"""Main window: sidebar navigation and the page stack."""

from __future__ import annotations

import logging

from PySide6.QtCore import QByteArray, QEasingCurve, QSize, Qt, QTimer, QVariantAnimation
from PySide6.QtGui import QCloseEvent, QIcon, QPixmap
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from sieve import APP_NAME, AUTHOR, __version__, paths
from sieve.context import AppContext
from sieve.tools import Tool, all_tools
from sieve.ui.icons import icon
from sieve.ui.pages.about import AboutPage
from sieve.ui.pages.home import HomePage
from sieve.ui.pages.settings import SettingsPage
from sieve.ui.updates import UpdateController

log = logging.getLogger(__name__)

HOME, SETTINGS, ABOUT = "home", "settings", "about"
TOOL_PREFIX = "tool:"
KEY_ROLE = Qt.ItemDataRole.UserRole
LABEL_ROLE = Qt.ItemDataRole.UserRole + 1
SIDEBAR_EXPANDED = 230
SIDEBAR_COLLAPSED = 64


class MainWindow(QMainWindow):
    def __init__(self, context: AppContext) -> None:
        super().__init__()
        self._context = context
        self._tools: dict[str, Tool] = {tool.id: tool for tool in all_tools()}
        self._pages: dict[str, QWidget] = {}
        self.updates = UpdateController(context, self)

        self.setWindowTitle(f"{APP_NAME} — by {AUTHOR}")
        self.setWindowIcon(QIcon(str(paths.resource_path("assets", "icon.ico"))))
        self.setMinimumSize(980, 640)

        central = QWidget()
        root = QHBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        root.addWidget(self._build_sidebar())
        self._stack = QStackedWidget()
        root.addWidget(self._stack, 1)
        self.setCentralWidget(central)

        home = HomePage(context, list(self._tools.values()))
        home.open_tool.connect(lambda tool_id: self.navigate(TOOL_PREFIX + tool_id))
        home.open_settings.connect(lambda: self.navigate(SETTINGS))
        settings = SettingsPage(context)
        settings.token_changed.connect(home.refresh)
        self._add_page(HOME, home)
        self._add_page(SETTINGS, settings)
        self._add_page(ABOUT, AboutPage(self.updates))

        self._restore_geometry()
        self.navigate(HOME)

    # --------------------------------------------------------------- sidebar
    def _build_sidebar(self) -> QFrame:
        sidebar = QFrame()
        sidebar.setObjectName("Sidebar")
        sidebar.setFixedWidth(SIDEBAR_EXPANDED)
        self._sidebar = sidebar
        self._sidebar_expanded = True
        layout = QVBoxLayout(sidebar)
        layout.setContentsMargins(0, 18, 0, 14)
        layout.setSpacing(4)

        self._brand = QHBoxLayout()
        self._brand.setContentsMargins(18, 0, 12, 10)
        self._brand.setSpacing(10)
        self._logo = QLabel()
        pixmap = QPixmap(str(paths.resource_path("assets", "icon.png")))
        if not pixmap.isNull():
            self._logo.setPixmap(
                pixmap.scaled(
                    34, 34,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
            )
        self._brand.addWidget(self._logo)
        self._titles = QWidget()
        titles = QVBoxLayout(self._titles)
        titles.setContentsMargins(0, 0, 0, 0)
        titles.setSpacing(0)
        name = QLabel(APP_NAME)
        name.setObjectName("BrandName")
        version = QLabel(f"v{__version__}")
        version.setObjectName("BrandVersion")
        titles.addWidget(name)
        titles.addWidget(version)
        self._brand.addWidget(self._titles)
        self._brand.addStretch(1)
        self._toggle_button = QPushButton()
        self._toggle_button.setObjectName("SidebarToggle")
        self._toggle_button.setFixedSize(34, 34)
        self._toggle_button.setIconSize(QSize(20, 20))
        self._toggle_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self._toggle_button.clicked.connect(
            lambda: self.set_sidebar_expanded(not self._sidebar_expanded)
        )
        self._brand.addWidget(self._toggle_button)
        layout.addLayout(self._brand)

        self._main_nav = self._nav_list()
        self._add_nav_item(self._main_nav, "Home", HOME, "home")
        self._tools_header: QListWidgetItem | None = None
        if self._tools:
            header = QListWidgetItem("TOOLS")
            header.setFlags(Qt.ItemFlag.NoItemFlags)
            header.setData(KEY_ROLE, None)
            self._main_nav.addItem(header)
            self._tools_header = header
            for tool in self._tools.values():
                self._add_nav_item(self._main_nav, tool.name, TOOL_PREFIX + tool.id, tool.icon)
        layout.addWidget(self._main_nav, 1)

        self._bottom_nav = self._nav_list()
        self._add_nav_item(self._bottom_nav, "Settings", SETTINGS, "settings")
        self._add_nav_item(self._bottom_nav, "About", ABOUT, "info")
        self._bottom_nav.setFixedHeight(self._bottom_nav.sizeHintForRow(0) * 2 + 12)
        layout.addWidget(self._bottom_nav)

        self._footer = QLabel(f"by {AUTHOR}")
        self._footer.setObjectName("Footer")
        self._footer.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addSpacing(6)
        layout.addWidget(self._footer)

        self._sidebar_animation = QVariantAnimation(self)
        self._sidebar_animation.setDuration(160)
        self._sidebar_animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._sidebar_animation.valueChanged.connect(lambda width: sidebar.setFixedWidth(int(width)))
        self._sidebar_animation.finished.connect(self._on_sidebar_animation_finished)
        self._apply_sidebar_contents(expanded=True)
        return sidebar

    def set_sidebar_expanded(self, expanded: bool, animate: bool = True) -> None:
        """Expand to show labels, or collapse to an icon rail to give tools more room."""
        if expanded == self._sidebar_expanded:
            return
        self._sidebar_expanded = expanded
        target = SIDEBAR_EXPANDED if expanded else SIDEBAR_COLLAPSED
        if not expanded:
            self._apply_sidebar_contents(expanded=False)
        # When expanding, labels appear once the sidebar has grown (see
        # _on_sidebar_animation_finished), so text never wraps mid-animation.
        if animate:
            self._sidebar_animation.stop()
            self._sidebar_animation.setStartValue(self._sidebar.width())
            self._sidebar_animation.setEndValue(target)
            self._sidebar_animation.start()
        else:
            self._sidebar.setFixedWidth(target)
            self._on_sidebar_animation_finished()

    def _on_sidebar_animation_finished(self) -> None:
        if self._sidebar_expanded:
            self._apply_sidebar_contents(expanded=True)

    def is_sidebar_expanded(self) -> bool:
        return self._sidebar_expanded

    def _apply_sidebar_contents(self, expanded: bool) -> None:
        self._logo.setVisible(expanded)
        self._titles.setVisible(expanded)
        self._footer.setVisible(expanded)
        if expanded:
            self._brand.setContentsMargins(18, 0, 12, 10)
        else:
            margin = (SIDEBAR_COLLAPSED - self._toggle_button.width()) // 2
            self._brand.setContentsMargins(margin, 0, margin, 10)
        self._toggle_button.setIcon(icon("collapse" if expanded else "menu"))
        self._toggle_button.setToolTip("Collapse sidebar" if expanded else "Expand sidebar")
        if self._tools_header is not None:
            self._tools_header.setHidden(not expanded)
        for nav in (self._main_nav, self._bottom_nav):
            nav.setProperty("collapsed", not expanded)
            nav.style().unpolish(nav)
            nav.style().polish(nav)
            for row in range(nav.count()):
                item = nav.item(row)
                label = item.data(LABEL_ROLE)
                if label is None:
                    continue
                item.setText(label if expanded else "")
                item.setToolTip("" if expanded else label)

    def _nav_list(self) -> QListWidget:
        nav = QListWidget()
        nav.setObjectName("NavList")
        nav.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        nav.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        nav.setTextElideMode(Qt.TextElideMode.ElideRight)
        nav.setCursor(Qt.CursorShape.PointingHandCursor)
        nav.setIconSize(QSize(20, 20))
        nav.itemClicked.connect(lambda item: self.navigate(item.data(KEY_ROLE)))
        return nav

    @staticmethod
    def _add_nav_item(nav: QListWidget, label: str, key: str, icon_name: str) -> None:
        item = QListWidgetItem(icon(icon_name), label)
        item.setData(KEY_ROLE, key)
        item.setData(LABEL_ROLE, label)
        nav.addItem(item)

    # ------------------------------------------------------------ navigation
    def _add_page(self, key: str, page: QWidget) -> None:
        self._pages[key] = page
        self._stack.addWidget(page)

    def navigate(self, key: str | None) -> None:
        if not key:
            return
        if key not in self._pages and key.startswith(TOOL_PREFIX):
            tool = self._tools.get(key.removeprefix(TOOL_PREFIX))
            if tool is None:
                return
            try:
                self._add_page(key, tool.create_widget(self._context))
            except Exception:
                log.exception("Could not open tool %s", tool.id)
                QMessageBox.critical(
                    self, tool.name, "The tool could not be opened. See the log file for details."
                )
                return
        page = self._pages.get(key)
        if page is None:
            return
        self._stack.setCurrentWidget(page)
        self._sync_selection(key)
        # Tools get the full width; the other pages show the full sidebar.
        self.set_sidebar_expanded(not key.startswith(TOOL_PREFIX), animate=self.isVisible())

    def _sync_selection(self, key: str) -> None:
        for nav in (self._main_nav, self._bottom_nav):
            nav.blockSignals(True)
            nav.clearSelection()
            for row in range(nav.count()):
                item = nav.item(row)
                if item.data(KEY_ROLE) == key:
                    nav.setCurrentItem(item)
            nav.blockSignals(False)

    def current_page(self) -> QWidget | None:
        return self._stack.currentWidget()

    def current_page_key(self) -> str | None:
        current = self._stack.currentWidget()
        return next((key for key, page in self._pages.items() if page is current), None)

    def page_keys(self) -> list[str]:
        """Keys of every page, including tool pages that have not been opened yet."""
        tool_keys = [TOOL_PREFIX + tool_id for tool_id in self._tools]
        return [HOME, *tool_keys, SETTINGS, ABOUT]

    # ------------------------------------------------------------- lifecycle
    def start_background_checks(self) -> None:
        if self._context.settings.check_updates_on_startup:
            QTimer.singleShot(1500, lambda: self.updates.check(manual=False))

    def _restore_geometry(self) -> None:
        saved = self._context.settings.window_geometry
        if not saved or not self.restoreGeometry(QByteArray.fromBase64(saved.encode("ascii"))):
            self.resize(1180, 760)

    def closeEvent(self, event: QCloseEvent) -> None:  # noqa: N802 (Qt override)
        for page in self._pages.values():
            save_state = getattr(page, "save_state", None)
            if callable(save_state):
                try:
                    save_state()
                except Exception:
                    log.exception("Could not save page state")
        geometry = bytes(self.saveGeometry().toBase64()).decode("ascii")
        self._context.settings.window_geometry = geometry
        try:
            self._context.save_settings()
        except OSError:
            log.exception("Could not save settings")
        super().closeEvent(event)
