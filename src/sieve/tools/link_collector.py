"""Link Collector: collect the links on a list of pages (directories, exhibitor
lists, search results), filtered and ready for Email Scraper.

Layout: options on top, then Pages | Results side by side, like Email Scraper.
"""

from __future__ import annotations

import logging
import time

from PySide6.QtCore import QByteArray, Qt, QTimer
from PySide6.QtGui import QColor, QGuiApplication, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QSizePolicy,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QWidget,
)

from sieve.context import AppContext
from sieve.core.email_scraper import BROWSER_OFF, BROWSER_SMART, HttpFetcher
from sieve.core.link_collector import (
    ALL,
    BLOCKED,
    EXTERNAL,
    FAILED,
    INTERNAL,
    NO_LINKS,
    PAGE_CHOICES,
    PARTIAL,
    READ,
    STATUSES,
    CollectOptions,
    CollectSummary,
    Link,
    LinkFilterSettings,
    PageResult,
    collect_links,
    entry_key,
    parse_pages,
    parse_rules,
)
from sieve.proxy import ProxyPool
from sieve.storage import JsonDocument
from sieve.tools.base import Tool
from sieve.tools.email_scraper import (
    BROWSER_CHOICES,
    BROWSER_POOL_LIMIT,
    LOG_LINE_LIMIT,
    VIA_LABELS,
    _duration,
    _editor,
    _table,
)
from sieve.ui import theme
from sieve.ui.link_filters import LinkFiltersDialog, load_exclude_lists
from sieve.ui.routing import SendToButton, notify_finished
from sieve.ui.tasks import BackgroundTask, run_in_background
from sieve.ui.widgets import (
    SegmentedControl,
    ToolPage,
    compact_button,
    flash_button,
    format_number,
    muted_label,
    primary_button,
    stats_html,
    titled_panel,
)

log = logging.getLogger(__name__)

TOOL_ID = "link_collector"
SESSION_DOCUMENT = "link_collector_session"
WORKER_CHOICES = (1, 3, 5, 10, 15, 20)
SCOPE_CHOICES = (
    (ALL, "All", "Keep every link on the pages."),
    (EXTERNAL, "Other sites", "Keep only links to other websites, e.g. the companies a directory lists."),
    (INTERNAL, "Same site", "Keep only links within the page's own website."),
)
STATUS_LABELS = {READ: "Read", PARTIAL: "Incomplete", NO_LINKS: "No links", BLOCKED: "Blocked", FAILED: "Failed"}
STATUS_COLORS = {
    READ: theme.SUCCESS, PARTIAL: theme.WARNING, NO_LINKS: theme.TEXT_MUTED,
    BLOCKED: theme.WARNING, FAILED: theme.DANGER,
}
STATUS_TIPS = {
    PARTIAL: "Some pages of this list were not read. The note says which and why.",
    NO_LINKS: "The page opened, but no link passed the filters.",
    BLOCKED: "Bot protection or a captcha answered. Retrying with proxies may help.",
    FAILED: "The page could not be opened.",
}
RETRYABLE = (FAILED, BLOCKED, PARTIAL)


def _pages_read(result: PageResult) -> str:
    """"12", or "12 / 47" when the list shows how many pages it has."""
    read = result.pages_read or (1 if result.status in (READ, NO_LINKS) else 0)
    return f"{read} / {result.expected_pages}" if result.expected_pages else str(read)


class LinkCollectorTool(Tool):
    id = TOOL_ID
    name = "Link Collector"
    description = "Collects the links on a list of pages, such as directories or exhibitor lists."
    category = "Scraping"
    icon = "globe"

    def self_check(self) -> None:
        import bs4  # noqa: F401
        import requests  # noqa: F401

        from sieve.core.browser import ensure_browser_support

        ensure_browser_support()

    def create_widget(self, context: AppContext) -> QWidget:
        return LinkCollectorPage(context)


def run_job(
    pages: list[str],
    options: CollectOptions,
    pool: ProxyPool | None,
    progress=None,
    cancelled=None,
) -> CollectSummary:
    proxies: dict[int, object] = {}

    def proxy_for(index: int):
        if pool and index not in proxies:
            proxies[index] = pool.next()
        return proxies.get(index)

    def fetcher_for(index: int) -> HttpFetcher:
        proxy = proxy_for(index)
        return HttpFetcher(proxy.for_requests() if proxy else None)

    if options.browser == BROWSER_OFF:
        return collect_links(pages, fetcher_for, options, progress=progress, cancelled=cancelled)

    from sieve.core.browser import BrowserFetcher, BrowserPool

    browsers = BrowserPool(size=min(BROWSER_POOL_LIMIT, options.workers), uses_proxies=bool(pool))

    def browser_for(index: int) -> BrowserFetcher:
        proxy = proxy_for(index)
        return BrowserFetcher(browsers, proxy.for_playwright() if proxy else None)

    try:
        return collect_links(pages, fetcher_for, options, progress=progress, cancelled=cancelled,
                             browser_for=browser_for)
    finally:
        browsers.close()


class LinkCollectorPage(ToolPage):
    def __init__(self, context: AppContext) -> None:
        super().__init__(LinkCollectorTool.name, LinkCollectorTool.description)
        self._context = context
        self._prefs = context.tool_settings(TOOL_ID)
        self._session_doc = JsonDocument(SESSION_DOCUMENT)
        self._task: BackgroundTask | None = None
        self._persist_session = True
        self._home_pages = False
        self._reset_state()

        self._save_timer = QTimer(self)
        self._save_timer.setSingleShot(True)
        self._save_timer.setInterval(3000)
        self._save_timer.timeout.connect(self._save_session)
        self._clock = QTimer(self)
        self._clock.setInterval(1000)
        self._clock.timeout.connect(self._update_progress_label)

        self.content.addWidget(self._build_toolbar())
        self._splitter = QSplitter(Qt.Orientation.Horizontal)
        self._splitter.setChildrenCollapsible(False)
        self._splitter.setHandleWidth(12)
        self._splitter.addWidget(self._build_pages_panel())
        self._splitter.addWidget(self._build_results_panel())
        self._splitter.setSizes([4, 7])
        saved = self._prefs.get("splitter")
        if isinstance(saved, str) and saved:
            self._splitter.restoreState(QByteArray.fromBase64(saved.encode("ascii")))
        self._splitter.splitterMoved.connect(self._save_splitter)
        self.content.addWidget(self._splitter, 1)

        copy_shortcut = QShortcut(QKeySequence("Ctrl+Shift+C"), self)
        copy_shortcut.activated.connect(self._copy_links)

        self._refresh_proxy_option()
        self._restore_session()

    def _reset_state(self) -> None:
        self._results: list[PageResult] = []
        #: key -> (link, list entry it came from), in the order found
        self._links: dict[str, tuple[Link, str]] = {}
        self._rejected: dict[str, str] = {}
        self._total = 0
        self._started_at = 0.0

    # --------------------------------------------------------------- toolbar
    def _build_toolbar(self) -> QFrame:
        bar = QFrame()
        bar.setObjectName("Toolbar")
        row = QHBoxLayout(bar)
        row.setContentsMargins(14, 8, 14, 8)
        row.setSpacing(14)

        self._scope_control = SegmentedControl(list(SCOPE_CHOICES), self)
        self._scope_control.changed.connect(self._on_scope)
        scope = self._prefs.get("scope", ALL)
        self._scope = scope if scope in (ALL, EXTERNAL, INTERNAL) else ALL
        self._scope_control.set_current(self._scope)
        row.addLayout(self._scope_control.layout)

        self._home_only = QCheckBox("Home pages only")
        self._home_only.setToolTip(
            "Turn every link into its website's home page, once per site.\n"
            "Ready to send to Email Scraper."
        )
        self._home_only.setChecked(bool(self._prefs.get("home_pages_only", False)))
        self._home_only.toggled.connect(self._save_options)
        filters = compact_button("Filters...", "Social and file links, tracking parameters and your exclude rules.")
        filters.clicked.connect(self._edit_filters)

        self._use_proxies = QCheckBox("Use proxies")
        self._use_proxies.setChecked(bool(self._prefs.get("use_proxies", False)))
        self._use_proxies.toggled.connect(self._save_options)

        self._browser = QComboBox()
        for value, label, tip in BROWSER_CHOICES:
            self._browser.addItem(label, value)
            self._browser.setItemData(self._browser.count() - 1, tip, Qt.ItemDataRole.ToolTipRole)
        index = self._browser.findData(self._prefs.get("browser", BROWSER_SMART))
        self._browser.setCurrentIndex(max(index, 0))
        self._browser.setToolTip(
            "When to open pages in a real browser instead of a plain request.\n"
            "Smart: only for blocked pages, pages built with JavaScript or pages showing no links."
        )
        self._browser.currentIndexChanged.connect(self._save_options)

        self._workers = QComboBox()
        for count in WORKER_CHOICES:
            self._workers.addItem(f"{count} at a time", count)
        index = self._workers.findData(int(self._prefs.get("workers", 5)))
        self._workers.setCurrentIndex(index if index >= 0 else self._workers.findData(5))
        self._workers.setToolTip(
            "How many pages are read at the same time.\n"
            "Requests to the same site are always spaced out."
        )
        self._workers.currentIndexChanged.connect(self._save_options)

        for widget in (self._home_only, filters, self._use_proxies):
            widget.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
            row.addWidget(widget)
        row.addStretch(1)
        row.addWidget(self._browser)
        row.addWidget(self._workers)
        return bar

    def _on_scope(self, scope: str) -> None:
        self._scope = scope
        self._save_options()

    def _edit_filters(self) -> None:
        LinkFiltersDialog(self._prefs, self._context.save_settings, self).exec()

    def _refresh_proxy_option(self) -> None:
        pool = self._context.proxy_pool()
        if pool:
            self._use_proxies.setEnabled(True)
            self._use_proxies.setText(f"Use proxies ({len(pool)})")
            self._use_proxies.setToolTip("Rotate through the proxies from Settings, one per list entry.")
        else:
            self._use_proxies.setEnabled(False)
            self._use_proxies.setText("Use proxies")
            reason = "turned off" if self._context.settings.proxies else "empty"
            self._use_proxies.setToolTip(f"The proxy list in Settings is {reason}.")

    def showEvent(self, event) -> None:  # noqa: N802 (Qt override)
        self._refresh_proxy_option()
        super().showEvent(event)

    def _save_options(self) -> None:
        self._prefs.update(
            scope=self._scope,
            home_pages_only=self._home_only.isChecked(),
            use_proxies=self._use_proxies.isChecked(),
            browser=self._browser.currentData(),
            workers=self._workers.currentData(),
            max_pages=self._max_pages.currentData() if hasattr(self, "_max_pages") else 1,
        )
        self._context.save_settings()

    def _save_splitter(self) -> None:
        self._prefs["splitter"] = bytes(self._splitter.saveState().toBase64()).decode("ascii")
        self._context.save_settings()

    # ----------------------------------------------------------------- pages
    def _build_pages_panel(self) -> QFrame:
        panel, body, header = titled_panel("Pages")
        self._pages_info = muted_label(wrap=False)
        header.addWidget(self._pages_info)
        header.addStretch(1)
        paste = compact_button("Paste", "Replace the list with the clipboard contents.")
        clear = compact_button("Clear", "Clear the list.")
        paste.clicked.connect(self._paste_pages)
        clear.clicked.connect(lambda: self._pages.clear())
        header.addWidget(paste)
        header.addWidget(clear)

        self._pages = _editor(
            "One page per line, e.g.\nhttps://expo.com/exhibitors\n\n"
            "{1-40} stands for the numbers 1 to 40:\nhttps://directory.org/companies?page={1-40}"
        )
        self._pages.textChanged.connect(self._update_pages_info)
        body.addWidget(self._pages, 1)

        follow = QHBoxLayout()
        follow.setSpacing(8)
        follow.addWidget(muted_label("Read per page:", wrap=False))
        self._max_pages = QComboBox()
        for count in PAGE_CHOICES:
            self._max_pages.addItem("Only that page" if count == 1 else f"Up to {count} pages", count)
        index = self._max_pages.findData(int(self._prefs.get("max_pages", 1)))
        self._max_pages.setCurrentIndex(max(index, 0))
        self._max_pages.setToolTip(
            "For lists split over several pages: follow the \"Next\" link (Next, Sonraki, Weiter, »...)\n"
            "and read the following pages too, up to this many per entry."
        )
        self._max_pages.currentIndexChanged.connect(self._save_options)
        follow.addWidget(self._max_pages)
        follow.addStretch(1)
        body.addLayout(follow)

        self._progress = QProgressBar()
        self._progress.setRange(0, 100)
        self._progress.hide()
        self._progress_label = muted_label(wrap=False)
        self._progress_label.hide()
        body.addWidget(self._progress)
        body.addWidget(self._progress_label)

        footer = QHBoxLayout()
        footer.setSpacing(8)
        self._start_button = primary_button("Start")
        self._start_button.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._start_button.clicked.connect(self._start)
        self._stop_button = QPushButton("Stop")
        self._stop_button.setToolTip("Finish the pages in progress and stop.")
        self._stop_button.setEnabled(False)
        self._stop_button.clicked.connect(self._stop)
        footer.addWidget(self._start_button, 1)
        footer.addWidget(self._stop_button)
        body.addLayout(footer)
        self._update_pages_info()
        return panel

    def _update_pages_info(self) -> None:
        self._pages_info.setText(f"· {format_number(len(parse_pages(self._pages.toPlainText())))} pages")

    def _paste_pages(self) -> None:
        text = QGuiApplication.clipboard().text()
        if text:
            self._pages.setPlainText(text)

    # --------------------------------------------------------------- results
    def _build_results_panel(self) -> QFrame:
        panel, body, header = titled_panel("Results")
        header.addStretch(1)
        self._copy_button = primary_button("Copy links")
        self._copy_button.setToolTip("Copy all unique links, one per line (Ctrl+Shift+C).")
        self._copy_button.clicked.connect(self._copy_links)
        header.addWidget(self._copy_button)

        self._stats = QLabel()
        self._stats.setObjectName("Stats")
        self._stats.setTextFormat(Qt.TextFormat.RichText)
        body.addWidget(self._stats)

        self._tabs = QTabWidget()
        self._tabs.setUsesScrollButtons(False)
        self._links_view = _editor("Links will appear here as pages finish.", read_only=True)
        self._details_table = _table(["Link", "Text", "Found on"], stretch=0)
        self._pages_table = _table(["Page", "Status", "Kept", "New", "Pages", "Time", "Via", "Note"], stretch=0)
        self._rejected_table = _table(["Link", "Reason"], stretch=0)
        self._log = _editor("", read_only=True)
        self._log.setMaximumBlockCount(LOG_LINE_LIMIT)
        self._tabs.addTab(self._links_view, "Links")
        self._tabs.addTab(self._details_table, "Link details")
        self._tabs.addTab(self._pages_table, "Pages")
        self._tabs.addTab(self._rejected_table, "Filtered out")
        self._tabs.addTab(self._log, "Log")
        body.addWidget(self._tabs, 1)

        footer = QHBoxLayout()
        footer.setSpacing(6)
        self._copy_details_button = compact_button(
            "Copy link details", "Copy links with their text and page as a table (pastes into Excel)."
        )
        self._copy_pages_button = compact_button("Copy pages table", "Copy the Pages table (pastes into Excel).")
        self._retry_button = compact_button(
            "Retry failed", "Put the pages that failed or were blocked back into the list.\n"
            "Blocked pages often work again with proxies turned on."
        )
        self._copy_details_button.clicked.connect(self._copy_details)
        self._copy_pages_button.clicked.connect(self._copy_pages)
        self._retry_button.clicked.connect(self._retry_failed)
        footer.addWidget(self._copy_details_button)
        self._send_button = SendToButton(TOOL_ID, self._links_text)
        footer.addWidget(self._send_button)
        footer.addWidget(self._copy_pages_button)
        footer.addWidget(self._retry_button)
        footer.addStretch(1)
        body.addLayout(footer)
        return panel

    # ------------------------------------------------------------------- run
    def _filter_settings(self) -> LinkFilterSettings:
        settings = LinkFilterSettings.from_dict(self._prefs.get("filters", {}))
        settings.scope = self._scope
        settings.home_pages_only = self._home_only.isChecked()
        settings.exclude = parse_rules(load_exclude_lists().text)
        return settings

    def _start(self) -> None:
        if self._task is not None:
            return
        pages = parse_pages(self._pages.toPlainText())
        if not pages:
            self._pages.setFocus()
            flash_button(self._start_button, "Add pages first")
            return
        if self._results:
            answer = QMessageBox.question(
                self, LinkCollectorTool.name, "Starting a new run clears the current results. Continue?"
            )
            if answer != QMessageBox.StandardButton.Yes:
                return

        pool = self._context.proxy_pool() if self._use_proxies.isChecked() else None
        filters = self._filter_settings()
        options = CollectOptions(
            filters=filters, workers=self._workers.currentData(), browser=self._browser.currentData(),
            max_pages=self._max_pages.currentData(),
        )
        self._clear_results()
        self._home_pages = filters.home_pages_only
        self._total = len(pages)
        self._started_at = time.monotonic()
        self._set_running(True)
        scope = {ALL: "all links", EXTERNAL: "other sites", INTERNAL: "same site"}[filters.scope]
        self._log.appendPlainText(
            f"Started {time.strftime('%Y-%m-%d %H:%M:%S')} · {len(pages)} pages · {scope}"
            + (" · home pages only" if filters.home_pages_only else "")
            + (f" · up to {options.max_pages} pages each" if options.max_pages > 1 else "")
            + f" · {options.workers} parallel · browser {options.browser}"
            + (f" · {len(pool)} proxies" if pool else "")
            + (f" · {len(filters.exclude)} exclude rules" if filters.exclude else "")
        )
        self._task = run_in_background(
            run_job, pages, options, pool,
            on_success=self._on_done, on_error=self._on_error, on_progress=self._on_page_done,
        )

    def _stop(self) -> None:
        if self._task:
            self._task.cancel()
            self._stop_button.setEnabled(False)
            self._stop_button.setText("Stopping...")

    def _set_running(self, running: bool) -> None:
        self._start_button.setEnabled(not running)
        self._stop_button.setEnabled(running)
        self._stop_button.setText("Stop")
        self._pages.setReadOnly(running)
        self._progress.setVisible(running)
        self._progress_label.setVisible(running)
        if running:
            self._progress.setValue(0)
            self._update_progress_label()
            self._clock.start()
        else:
            self._clock.stop()

    def _update_progress_label(self) -> None:
        done = len(self._results)
        elapsed = time.monotonic() - self._started_at if self._started_at else 0
        text = f"{format_number(done)} / {format_number(self._total)} pages · {_duration(elapsed)}"
        if done and done < self._total:
            text += f" · about {_duration(elapsed / done * (self._total - done))} left"
        self._progress_label.setText(text)

    def _on_page_done(self, result: PageResult, total: int) -> None:
        self._add_result(result)
        self._progress.setValue(int(len(self._results) * 100 / max(total, 1)))
        self._update_progress_label()
        self._update_stats()
        self._save_timer.start()

    def _on_done(self, summary: CollectSummary) -> None:
        self._task = None
        self._set_running(False)
        elapsed = time.monotonic() - self._started_at
        word = "Stopped" if summary.stopped else "Finished"
        read = sum(1 for result in summary.results if result.status == READ)
        self._log.appendPlainText(
            f"{word} after {_duration(elapsed)} · {len(self._links)} unique links "
            f"from {read} of {len(summary.results)} pages"
        )
        self._update_stats()
        self._save_session()
        notify_finished(self)

    def _on_error(self, exc: Exception) -> None:
        self._task = None
        self._set_running(False)
        log.error("Link collecting failed", exc_info=exc)
        self._save_session()
        QMessageBox.critical(self, LinkCollectorTool.name, f"An unexpected error occurred:\n{exc}")

    # --------------------------------------------------------- result views
    def _clear_results(self) -> None:
        self._reset_state()
        self._links_view.clear()
        self._log.clear()
        for table in (self._pages_table, self._details_table, self._rejected_table):
            table.setRowCount(0)
        self._update_stats()

    def _add_result(self, result: PageResult, write_log: bool = True) -> None:
        self._results.append(result)
        new_lines: list[str] = []
        for link in result.links:
            key = entry_key(link.url, self._home_pages)
            if key not in self._links:
                self._links[key] = (link, result.url)
                new_lines.append(link.url)
                self._append_row(self._details_table, [link.url, link.text, link.page])
        if new_lines:
            self._links_view.appendPlainText("\n".join(new_lines))
        for url, reason in result.rejected:
            if url not in self._rejected:
                self._rejected[url] = reason
                self._append_row(self._rejected_table, [url, reason])

        moved = result.final_url if result.final_url.rstrip("/") != result.url.rstrip("/") else ""
        note = result.error or result.note or moved
        row = self._append_row(self._pages_table, [
            result.url,
            STATUS_LABELS.get(result.status, result.status),
            str(len(result.links)),
            str(len(new_lines)),
            _pages_read(result),
            f"{result.elapsed:.1f}s",
            VIA_LABELS.get(result.via, result.via),
            note,
        ])
        status_item = self._pages_table.item(row, 1)
        status_item.setForeground(QColor(STATUS_COLORS.get(result.status, theme.TEXT)))
        if result.status in STATUS_TIPS:
            status_item.setToolTip(STATUS_TIPS[result.status])
        if result.status == PARTIAL:
            self._pages_table.item(row, 7).setForeground(QColor(theme.WARNING))
        self._pages_table.item(row, 4).setToolTip(
            "Pages of the list read" + (f", out of the {result.expected_pages} the list shows"
                                        if result.expected_pages else "")
        )
        self._pages_table.item(row, 3).setToolTip("Links not already found on an earlier page of the list.")
        for column in (2, 3, 4, 5):
            self._pages_table.item(row, column).setTextAlignment(
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
            )
        if write_log and result.log:
            self._log.appendPlainText("\n".join(["", f"── {result.url}", *result.log]))

    @staticmethod
    def _append_row(table: QTableWidget, values: list[str]) -> int:
        row = table.rowCount()
        table.insertRow(row)
        for column, value in enumerate(values):
            item = QTableWidgetItem(value)
            item.setToolTip(value)
            table.setItem(row, column, item)
        return row

    def _update_stats(self) -> None:
        counts = dict.fromkeys(STATUSES, 0)
        for result in self._results:
            counts[result.status] = counts.get(result.status, 0) + 1
        items = [
            ("Pages", len(self._results), None),
            ("Links", len(self._links), theme.SUCCESS if self._links else None),
        ]
        for status in (PARTIAL, NO_LINKS, BLOCKED, FAILED):
            if counts[status]:
                items.append((STATUS_LABELS[status], counts[status], STATUS_COLORS[status]))
        if self._rejected:
            items.append(("Filtered out", len(self._rejected), theme.TEXT_MUTED))
        self._stats.setText(stats_html(items))
        has_links = bool(self._links)
        self._copy_button.setEnabled(has_links)
        self._send_button.setEnabled(has_links)
        self._copy_details_button.setEnabled(has_links)
        self._copy_pages_button.setEnabled(bool(self._results))
        retryable = sum(counts[status] for status in RETRYABLE)
        self._retry_button.setEnabled(retryable > 0 and self._task is None)
        self._tabs.setTabText(3, f"Filtered out ({len(self._rejected)})" if self._rejected else "Filtered out")

    # ------------------------------------------------------------- clipboard
    def _links_text(self) -> str:
        return "\n".join(link.url for link, _entry in self._links.values())

    def _copy_links(self) -> None:
        if self._links:
            QGuiApplication.clipboard().setText(self._links_text())
            flash_button(self._copy_button, "Copied ✓")

    def _copy_details(self) -> None:
        lines = ["Link\tText\tFound on"]
        for link, _entry in self._links.values():
            lines.append(f"{link.url}\t{link.text}\t{link.page}")
        QGuiApplication.clipboard().setText("\n".join(lines))
        flash_button(self._copy_details_button, "Copied ✓")

    def _copy_pages(self) -> None:
        lines = ["Page\tStatus\tKept\tPages read\tTime\tVia\tNote"]
        for result in self._results:
            lines.append(
                f"{result.url}\t{STATUS_LABELS.get(result.status, result.status)}\t{len(result.links)}\t"
                f"{_pages_read(result)}\t{result.elapsed:.1f}s\t{VIA_LABELS.get(result.via, result.via)}\t"
                f"{result.error or result.note or result.final_url}"
            )
        QGuiApplication.clipboard().setText("\n".join(lines))
        flash_button(self._copy_pages_button, "Copied ✓")

    def receive_text(self, text: str) -> None:
        if self._task is not None:
            QMessageBox.information(self, LinkCollectorTool.name, "Wait for the current run to finish first.")
            return
        self._pages.setPlainText(text)
        self._pages.setFocus()

    def _retry_failed(self) -> None:
        failed = [result.url for result in self._results if result.status in RETRYABLE]
        if failed:
            self._pages.setPlainText("\n".join(failed))
            self._pages.setFocus()

    # ---------------------------------------------------------------- session
    def _save_session(self) -> None:
        self._save_timer.stop()
        if not self._persist_session:
            return
        data = {
            "pages": self._pages.toPlainText(),
            "total": self._total,
            "home_pages": self._home_pages,
            "results": [
                {
                    "url": r.url, "status": r.status, "final_url": r.final_url, "pages": r.pages,
                    "error": r.error, "elapsed": round(r.elapsed, 2), "via": r.via,
                    "total_links": r.total_links, "pages_read": r.pages_read, "note": r.note,
                    "expected_pages": r.expected_pages,
                    "links": [[link.url, link.text, link.page] for link in r.links],
                    "rejected": [list(item) for item in r.rejected],
                }
                for r in self._results
            ],
        }
        try:
            self._session_doc.save(data)
        except OSError:
            log.exception("Could not save the link collector session")

    def _restore_session(self) -> None:
        data = self._session_doc.load()
        pages = data.get("pages")
        if isinstance(pages, str):
            self._pages.setPlainText(pages)
        self._home_pages = bool(data.get("home_pages", False))
        try:
            for item in data.get("results", []):
                result = PageResult(
                    url=item["url"], status=item["status"], final_url=item.get("final_url", ""),
                    pages=int(item.get("pages", 0)), error=item.get("error", ""),
                    elapsed=float(item.get("elapsed", 0)), via=item.get("via", "http"),
                    total_links=int(item.get("total_links", 0)),
                    pages_read=int(item.get("pages_read", 0)), note=item.get("note", ""),
                    expected_pages=item.get("expected_pages"),
                    links=[Link(*link) for link in item.get("links", [])],
                    rejected=[tuple(pair) for pair in item.get("rejected", [])],
                )
                self._add_result(result, write_log=False)
        except (KeyError, TypeError, ValueError):
            log.exception("Ignoring a damaged link collector session")
        self._total = int(data.get("total", len(self._results)) or 0)
        if self._results:
            self._log.appendPlainText(
                f"Restored the last run: {len(self._results)} of {self._total} pages. "
                "Detailed logs are kept only while the app is open."
            )
        self._update_stats()

    def save_state(self) -> None:
        """Called when the window closes: stop a running run and keep the results."""
        if self._task is not None:
            self._task.cancel()
        self._save_session()

    def load_demo(self) -> None:
        """Show sample results without network access or saving (CI screenshots)."""
        self._persist_session = False
        self._pages.setPlainText(
            "https://expo.example/exhibitors?page=1\nhttps://directory.example/defence\n"
            "https://guarded.example/members\nhttps://old.example/list"
        )
        self._clear_results()
        self._home_pages = True
        self._total = 4
        expo = "https://expo.example/exhibitors?page=1"
        samples = [
            PageResult(expo, READ, expo, 3, [
                Link("https://acme.example/", "ACME Defence Ltd", expo),
                Link("https://firma.example/", "Firma Savunma A.Ş.", "https://expo.example/exhibitors?page=2"),
                Link("https://beta.example/", "Beta Systems", "https://expo.example/exhibitors?page=3"),
            ], [("https://www.facebook.com/expo", "Social, share or app link"),
                ("https://expo.example/catalogue.pdf", "File download")], 64, "", "http", 4.2,
                pages_read=3, note="Last page reached (3 of 3 pages read)", expected_pages=3),
            PageResult("https://directory.example/defence", PARTIAL, "https://directory.example/defence", 1, [
                Link("https://acme.example/", "ACME", "https://directory.example/defence"),
                Link("https://gamma.example/", "Gamma Optics", "https://directory.example/defence"),
            ], [("https://directory.example/login", "Exclude rule: /login")], 41, "", "both", 6.8,
                pages_read=20, expected_pages=34,
                note="Stopped at the limit of 20 pages; there are more pages (the list has 34)"),
            PageResult("https://guarded.example/members", BLOCKED, pages=2,
                       error="Bot protection or captcha (HTTP 403)", via="both", elapsed=8.1),
            PageResult("https://old.example/list", FAILED, pages=1, error="Domain not found", elapsed=0.4),
        ]
        for result in samples:
            self._add_result(result, write_log=False)
        self._update_stats()
