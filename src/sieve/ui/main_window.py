"""Main window: sidebar navigation and the page stack."""

from __future__ import annotations

import logging

from PySide6.QtCore import QByteArray, Qt, QTimer
from PySide6.QtGui import QCloseEvent, QIcon, QPixmap
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from sieve import APP_NAME, AUTHOR, __version__, paths
from sieve.context import AppContext
from sieve.tools import Tool, all_tools
from sieve.ui.pages.about import AboutPage
from sieve.ui.pages.home import HomePage
from sieve.ui.pages.settings import SettingsPage
from sieve.ui.updates import UpdateController

log = logging.getLogger(__name__)

HOME, SETTINGS, ABOUT = "home", "settings", "about"
TOOL_PREFIX = "tool:"
KEY_ROLE = Qt.ItemDataRole.UserRole


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
        sidebar.setFixedWidth(230)
        layout = QVBoxLayout(sidebar)
        layout.setContentsMargins(0, 18, 0, 14)
        layout.setSpacing(4)

        brand = QHBoxLayout()
        brand.setContentsMargins(18, 0, 18, 10)
        logo = QLabel()
        pixmap = QPixmap(str(paths.resource_path("assets", "icon.png")))
        if not pixmap.isNull():
            logo.setPixmap(
                pixmap.scaled(
                    34, 34,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
            )
        brand.addWidget(logo)
        titles = QVBoxLayout()
        titles.setSpacing(0)
        name = QLabel(APP_NAME)
        name.setObjectName("BrandName")
        version = QLabel(f"v{__version__}")
        version.setObjectName("BrandVersion")
        titles.addWidget(name)
        titles.addWidget(version)
        brand.addLayout(titles)
        brand.addStretch(1)
        layout.addLayout(brand)

        self._main_nav = self._nav_list()
        self._add_nav_item(self._main_nav, "Ana Sayfa", HOME)
        if self._tools:
            header = QListWidgetItem("ARAÇLAR")
            header.setFlags(Qt.ItemFlag.NoItemFlags)
            header.setData(KEY_ROLE, None)
            self._main_nav.addItem(header)
            for tool in self._tools.values():
                self._add_nav_item(self._main_nav, tool.name, TOOL_PREFIX + tool.id)
        layout.addWidget(self._main_nav, 1)

        self._bottom_nav = self._nav_list()
        self._add_nav_item(self._bottom_nav, "Ayarlar", SETTINGS)
        self._add_nav_item(self._bottom_nav, "Hakkında", ABOUT)
        self._bottom_nav.setFixedHeight(self._bottom_nav.sizeHintForRow(0) * 2 + 12)
        layout.addWidget(self._bottom_nav)

        footer = QLabel(f"by {AUTHOR}")
        footer.setObjectName("Footer")
        footer.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addSpacing(6)
        layout.addWidget(footer)
        return sidebar

    def _nav_list(self) -> QListWidget:
        nav = QListWidget()
        nav.setObjectName("NavList")
        nav.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        nav.setCursor(Qt.CursorShape.PointingHandCursor)
        nav.itemClicked.connect(lambda item: self.navigate(item.data(KEY_ROLE)))
        return nav

    @staticmethod
    def _add_nav_item(nav: QListWidget, label: str, key: str) -> None:
        item = QListWidgetItem(label)
        item.setData(KEY_ROLE, key)
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
                    self, tool.name, "Araç açılırken bir hata oluştu. Ayrıntılar log dosyasında."
                )
                return
        page = self._pages.get(key)
        if page is None:
            return
        self._stack.setCurrentWidget(page)
        self._sync_selection(key)

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
        geometry = bytes(self.saveGeometry().toBase64()).decode("ascii")
        self._context.settings.window_geometry = geometry
        try:
            self._context.save_settings()
        except OSError:
            log.exception("Could not save settings")
        super().closeEvent(event)
