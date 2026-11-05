"""Email Scraper: find contact email addresses on a list of websites.

Layout: options on top, then Websites | Results side by side. Results appear
live as each site finishes and the last run is kept, so a long scan survives
closing the app or a crash.
"""

from __future__ import annotations

import logging
import time

from PySide6.QtCore import QByteArray, Qt, QTimer
from PySide6.QtGui import QColor, QGuiApplication, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QPlainTextEdit,
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
from sieve.core.email_filter import EmailFilter
from sieve.core.email_scraper import (
    BLOCKED,
    BROWSER_ALWAYS,
    BROWSER_OFF,
    BROWSER_SMART,
    DIRECT,
    EMPTY,
    FAILED,
    FORM_ONLY,
    FOUND,
    PARKED,
    STANDARD,
    STATUSES,
    FoundEmail,
    HttpFetcher,
    ScrapeOptions,
    ScrapeSummary,
    SiteResult,
    parse_sites,
    scrape_sites,
)
from sieve.proxy import ProxyPool
from sieve.storage import JsonDocument
from sieve.tools.base import Tool
from sieve.ui import theme
from sieve.ui.email_rules import EmailRulesDialog, load_filter
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

TOOL_ID = "email_scraper"
SESSION_DOCUMENT = "email_scraper_session"
LOG_LINE_LIMIT = 50_000
WORKER_CHOICES = (1, 3, 5, 10, 15, 20, 30)
MODE_HINTS = {
    STANDARD: "Scans each site's page, its contact pages, then common contact paths.",
    DIRECT: "Scans only the exact URLs you entered.",
}
STATUS_LABELS = {
    FOUND: "Found",
    FORM_ONLY: "Form only",
    EMPTY: "No emails",
    PARKED: "Parked",
    BLOCKED: "Blocked",
    FAILED: "Failed",
}
STATUS_TIPS = {
    FORM_ONLY: "No address on the site, only a contact form.",
    PARKED: "The domain is parked or for sale; there is no company site.",
    BLOCKED: "Bot protection or a captcha answered instead of the site. Retrying with proxies may help.",
    FAILED: "The site could not be opened.",
}
STATUS_COLORS = {
    FOUND: theme.SUCCESS,
    FORM_ONLY: theme.ACCENT_HOVER,
    EMPTY: theme.TEXT_MUTED,
    PARKED: theme.TEXT_MUTED,
    BLOCKED: theme.WARNING,
    FAILED: theme.DANGER,
}
RETRYABLE = (FAILED, BLOCKED)
BROWSER_CHOICES = (
    (BROWSER_SMART, "Browser: Smart",
     "Opens a site in Microsoft Edge only when a plain request is blocked,\n"
     "finds nothing, or the page needs JavaScript. Recommended."),
    (BROWSER_ALWAYS, "Browser: Always",
     "Opens every page in Microsoft Edge. Slowest, but sees what a visitor sees."),
    (BROWSER_OFF, "Browser: Off", "Plain requests only. Fastest."),
)
BROWSER_POOL_LIMIT = 4
VIA_LABELS = {"http": "Request", "browser": "Browser", "both": "Both tried"}
VIA_TIPS = {
    "http": "Read with a plain request.",
    "browser": "Opened in Microsoft Edge.",
    "both": "Also opened in Microsoft Edge, which found nothing more.",
}
HOW_LABELS = {
    "structured": "Site data (schema.org)",
    "decoded": "Hidden (decoded)",
    "link": "mailto link",
    "protected": "Cloudflare-protected",
    "text": "Page text",
    "source": "Page source",
    "script": "Script",
}


class EmailScraperTool(Tool):
    id = TOOL_ID
    name = "Email Scraper"
    description = "Finds contact email addresses on a list of websites, with junk filtering."
    category = "Scraping"
    icon = "mail"

    def self_check(self) -> None:
        import bs4  # noqa: F401
        import dns.resolver  # noqa: F401
        import requests  # noqa: F401

        from sieve.core.browser import ensure_browser_support

        ensure_browser_support()

    def create_widget(self, context: AppContext) -> QWidget:
        return EmailScraperPage(context)


def run_job(
    sites: list[str],
    options: ScrapeOptions,
    email_filter: EmailFilter | None,
    pool: ProxyPool | None,
    progress=None,
    cancelled=None,
) -> ScrapeSummary:
    proxies: dict[int, object] = {}

    def proxy_for(index: int):
        if pool and index not in proxies:
            proxies[index] = pool.next()
        return proxies.get(index)

    def fetcher_for(index: int) -> HttpFetcher:
        proxy = proxy_for(index)
        return HttpFetcher(proxy.for_requests() if proxy else None)

    if options.browser == BROWSER_OFF:
        return scrape_sites(sites, fetcher_for, email_filter, options, progress=progress, cancelled=cancelled)

    from sieve.core.browser import BrowserFetcher, BrowserPool

    browsers = BrowserPool(size=min(BROWSER_POOL_LIMIT, options.workers), uses_proxies=bool(pool))

    def browser_for(index: int) -> BrowserFetcher:
        proxy = proxy_for(index)
        return BrowserFetcher(browsers, proxy.for_playwright() if proxy else None)

    try:
        return scrape_sites(
            sites, fetcher_for, email_filter, options,
            progress=progress, cancelled=cancelled, browser_for=browser_for,
        )
    finally:
        browsers.close()


def _editor(placeholder: str, read_only: bool = False) -> QPlainTextEdit:
    editor = QPlainTextEdit()
    editor.setObjectName("Editor")
    editor.setPlaceholderText(placeholder)
    editor.setReadOnly(read_only)
    editor.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
    return editor


def _table(headers: list[str], stretch: int = 0) -> QTableWidget:
    table = QTableWidget(0, len(headers))
    table.setHorizontalHeaderLabels(headers)
    table.verticalHeader().hide()
    table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
    table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
    header = table.horizontalHeader()
    for column in range(len(headers)):
        mode = QHeaderView.ResizeMode.Stretch if column == stretch else QHeaderView.ResizeMode.ResizeToContents
        header.setSectionResizeMode(column, mode)
    return table


class EmailScraperPage(ToolPage):
    def __init__(self, context: AppContext) -> None:
        super().__init__(EmailScraperTool.name, EmailScraperTool.description)
        self._context = context
        self._prefs = context.tool_settings(TOOL_ID)
        self._session_doc = JsonDocument(SESSION_DOCUMENT)
        self._task: BackgroundTask | None = None
        self._persist_session = True
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
        self._splitter.addWidget(self._build_sites_panel())
        self._splitter.addWidget(self._build_results_panel())
        self._splitter.setSizes([4, 7])
        saved = self._prefs.get("splitter")
        if isinstance(saved, str) and saved:
            self._splitter.restoreState(QByteArray.fromBase64(saved.encode("ascii")))
        self._splitter.splitterMoved.connect(self._save_splitter)
        self.content.addWidget(self._splitter, 1)

        copy_shortcut = QShortcut(QKeySequence("Ctrl+Shift+C"), self)
        copy_shortcut.activated.connect(self._copy_emails)

        self._apply_mode(self._prefs.get("mode", STANDARD), save=False)
        self._refresh_proxy_option()
        self._restore_session()

    def _reset_state(self) -> None:
        self._results: list[SiteResult] = []
        self._emails: dict[str, tuple[FoundEmail, str]] = {}
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

        self._mode_control = SegmentedControl(
            [(STANDARD, "Standard", MODE_HINTS[STANDARD]), (DIRECT, "Direct", MODE_HINTS[DIRECT])],
            self,
        )
        self._mode_control.changed.connect(self._apply_mode)
        row.addLayout(self._mode_control.layout)

        self._filter_junk = QCheckBox("Filter junk")
        self._filter_junk.setToolTip(
            "Remove placeholders, no-reply, disposable, tracking and image-name addresses.\n"
            "Removed addresses are listed under Rejected."
        )
        self._filter_junk.setChecked(bool(self._prefs.get("filter_junk", True)))
        self._filter_junk.toggled.connect(self._save_options)
        rules = compact_button("Rules...", "Edit which addresses count as junk.")
        rules.clicked.connect(lambda: EmailRulesDialog(self).exec())

        self._use_proxies = QCheckBox("Use proxies")
        self._use_proxies.setChecked(bool(self._prefs.get("use_proxies", False)))
        self._use_proxies.toggled.connect(self._save_options)

        self._workers = QComboBox()
        for count in WORKER_CHOICES:
            self._workers.addItem(f"{count} at a time", count)
        saved_workers = int(self._prefs.get("workers", 10))
        index = self._workers.findData(saved_workers)
        self._workers.setCurrentIndex(index if index >= 0 else self._workers.findData(10))
        self._workers.setToolTip(
            "How many sites are scanned at the same time.\n"
            "Higher is faster but uses more bandwidth and may trigger rate limits."
        )
        self._workers.currentIndexChanged.connect(self._save_options)

        self._browser = QComboBox()
        for value, label, tip in BROWSER_CHOICES:
            self._browser.addItem(label, value)
            self._browser.setItemData(self._browser.count() - 1, tip, Qt.ItemDataRole.ToolTipRole)
        index = self._browser.findData(self._prefs.get("browser", BROWSER_SMART))
        self._browser.setCurrentIndex(max(index, 0))
        self._browser.setToolTip(
            "When to open sites in Microsoft Edge instead of a plain request.\n"
            "Smart: only for blocked, empty or JavaScript-only sites."
        )
        self._browser.currentIndexChanged.connect(self._save_options)

        for widget in (self._filter_junk, rules, self._use_proxies):
            widget.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
            row.addWidget(widget)
        row.addStretch(1)
        row.addWidget(self._browser)
        row.addWidget(self._workers)
        return bar

    def _apply_mode(self, mode: str, save: bool = True) -> None:
        self._mode = mode if mode in (STANDARD, DIRECT) else STANDARD
        self._mode_control.set_current(self._mode)
        if save:
            self._prefs["mode"] = self._mode
            self._context.save_settings()

    def _refresh_proxy_option(self) -> None:
        settings = self._context.settings
        pool = self._context.proxy_pool()
        if pool:
            self._use_proxies.setEnabled(True)
            self._use_proxies.setText(f"Use proxies ({len(pool)})")
            self._use_proxies.setToolTip("Rotate through the proxies from Settings, one per site.")
        else:
            self._use_proxies.setEnabled(False)
            self._use_proxies.setText("Use proxies")
            reason = "turned off" if settings.proxies else "empty"
            self._use_proxies.setToolTip(f"The proxy list in Settings is {reason}.")

    def showEvent(self, event) -> None:  # noqa: N802 (Qt override)
        self._refresh_proxy_option()
        super().showEvent(event)

    def _save_options(self) -> None:
        self._prefs.update(
            filter_junk=self._filter_junk.isChecked(),
            use_proxies=self._use_proxies.isChecked(),
            workers=self._workers.currentData(),
            browser=self._browser.currentData(),
        )
        self._context.save_settings()

    def _save_splitter(self) -> None:
        self._prefs["splitter"] = bytes(self._splitter.saveState().toBase64()).decode("ascii")
        self._context.save_settings()

    # ----------------------------------------------------------------- sites
    def _build_sites_panel(self) -> QFrame:
        panel, body, header = titled_panel("Websites")
        self._sites_info = muted_label(wrap=False)
        header.addWidget(self._sites_info)
        header.addStretch(1)
        paste = compact_button("Paste", "Replace the list with the clipboard contents.")
        clear = compact_button("Clear", "Clear the list.")
        paste.clicked.connect(self._paste_sites)
        clear.clicked.connect(lambda: self._sites.clear())
        header.addWidget(paste)
        header.addWidget(clear)

        self._sites = _editor("One website per line, e.g.\nacme.com\nhttps://www.example.org/contact")
        self._sites.textChanged.connect(self._update_sites_info)
        body.addWidget(self._sites, 1)

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
        self._stop_button.setToolTip("Finish the sites in progress and stop.")
        self._stop_button.setEnabled(False)
        self._stop_button.clicked.connect(self._stop)
        footer.addWidget(self._start_button, 1)
        footer.addWidget(self._stop_button)
        body.addLayout(footer)
        self._update_sites_info()
        return panel

    def _update_sites_info(self) -> None:
        count = len(parse_sites(self._sites.toPlainText()))
        self._sites_info.setText(f"· {format_number(count)} sites")

    def _paste_sites(self) -> None:
        text = QGuiApplication.clipboard().text()
        if text:
            self._sites.setPlainText(text)

    # --------------------------------------------------------------- results
    def _build_results_panel(self) -> QFrame:
        panel, body, header = titled_panel("Results")
        header.addStretch(1)
        self._copy_button = primary_button("Copy emails")
        self._copy_button.setToolTip("Copy all unique addresses, one per line (Ctrl+Shift+C).")
        self._copy_button.clicked.connect(self._copy_emails)
        header.addWidget(self._copy_button)

        self._stats = QLabel()
        self._stats.setObjectName("Stats")
        self._stats.setTextFormat(Qt.TextFormat.RichText)
        body.addWidget(self._stats)

        self._tabs = QTabWidget()
        self._tabs.setUsesScrollButtons(False)
        self._emails_view = _editor("Addresses will appear here as sites finish.", read_only=True)
        self._sites_table = _table(["Site", "Status", "Emails", "Pages", "Time", "Via", "Note"], stretch=0)
        self._emails_table = _table(["Email", "Site", "Found on", "How"], stretch=0)
        self._rejected_table = _table(["Address", "Reason"], stretch=0)
        self._log = _editor("", read_only=True)
        self._log.setMaximumBlockCount(LOG_LINE_LIMIT)
        self._tabs.addTab(self._emails_view, "Emails")
        self._tabs.addTab(self._emails_table, "Email details")
        self._tabs.addTab(self._sites_table, "Sites")
        self._tabs.addTab(self._rejected_table, "Rejected")
        self._tabs.addTab(self._log, "Log")
        body.addWidget(self._tabs, 1)

        footer = QHBoxLayout()
        footer.setSpacing(6)
        self._copy_details_button = compact_button(
            "Copy email details", "Copy addresses with their site and page as a table (pastes into Excel)."
        )
        self._copy_sites_button = compact_button(
            "Copy sites table", "Copy the Sites table (pastes into Excel)."
        )
        self._retry_button = compact_button(
            "Retry failed", "Put the sites that failed or were blocked back into the list.\n"
            "Blocked sites often work again with proxies turned on."
        )
        self._copy_details_button.clicked.connect(self._copy_details)
        self._copy_sites_button.clicked.connect(self._copy_sites)
        self._retry_button.clicked.connect(self._retry_failed)
        footer.addWidget(self._copy_details_button)
        self._send_button = SendToButton(TOOL_ID, lambda: "\n".join(self._emails))
        footer.addWidget(self._send_button)
        footer.addWidget(self._copy_sites_button)
        footer.addWidget(self._retry_button)
        footer.addStretch(1)
        body.addLayout(footer)
        return panel

    # ------------------------------------------------------------------- run
    def _start(self) -> None:
        if self._task is not None:
            return
        sites = parse_sites(self._sites.toPlainText())
        if not sites:
            self._sites.setFocus()
            flash_button(self._start_button, "Add websites first")
            return
        if self._results:
            answer = QMessageBox.question(
                self, EmailScraperTool.name,
                "Starting a new scan clears the current results. Continue?",
            )
            if answer != QMessageBox.StandardButton.Yes:
                return

        pool = self._context.proxy_pool() if self._use_proxies.isChecked() else None
        email_filter = load_filter() if self._filter_junk.isChecked() else None
        options = ScrapeOptions(
            mode=self._mode, workers=self._workers.currentData(), browser=self._browser.currentData()
        )

        self._clear_results()
        self._total = len(sites)
        self._started_at = time.monotonic()
        self._set_running(True)
        self._log.appendPlainText(
            f"Started {time.strftime('%Y-%m-%d %H:%M:%S')} · {len(sites)} sites · "
            f"{self._mode} mode · {options.workers} parallel · browser {options.browser}"
            + (f" · {len(pool)} proxies" if pool else "")
            + ("" if email_filter else " · junk filter off")
        )
        self._task = run_in_background(
            run_job,
            sites,
            options,
            email_filter,
            pool,
            on_success=self._on_done,
            on_error=self._on_error,
            on_progress=self._on_site_done,
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
        self._sites.setReadOnly(running)
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
        text = f"{format_number(done)} / {format_number(self._total)} sites · {_duration(elapsed)}"
        if done and done < self._total:
            remaining = elapsed / done * (self._total - done)
            text += f" · about {_duration(remaining)} left"
        self._progress_label.setText(text)

    def _on_site_done(self, result: SiteResult, total: int) -> None:
        self._add_result(result)
        self._progress.setValue(int(len(self._results) * 100 / max(total, 1)))
        self._update_progress_label()
        self._update_stats()
        if self._persist_session and not self._save_timer.isActive():
            self._save_timer.start()

    def _on_done(self, summary: ScrapeSummary) -> None:
        self._task = None
        self._set_running(False)
        elapsed = time.monotonic() - self._started_at
        word = "Stopped" if summary.stopped else "Finished"
        self._log.appendPlainText(
            f"{word} after {_duration(elapsed)} · {len(self._emails)} unique emails "
            f"from {summary.count(FOUND)} of {len(summary.results)} sites"
        )
        self._update_stats()
        self._save_session()
        notify_finished(self)

    def _on_error(self, exc: Exception) -> None:
        self._task = None
        self._set_running(False)
        log.error("Email scraping failed", exc_info=exc)
        self._save_session()
        QMessageBox.critical(self, EmailScraperTool.name, f"An unexpected error occurred:\n{exc}")

    # --------------------------------------------------------- result views
    def _clear_results(self) -> None:
        self._reset_state()
        self._emails_view.clear()
        self._log.clear()
        for table in (self._sites_table, self._emails_table, self._rejected_table):
            table.setRowCount(0)
        self._update_stats()

    def _add_result(self, result: SiteResult, write_log: bool = True) -> None:
        self._results.append(result)
        new_lines = []
        for found in result.emails:
            if found.email not in self._emails:
                self._emails[found.email] = (found, result.site)
                new_lines.append(found.email)
                self._append_row(self._emails_table, [
                    found.email, result.site, found.page, HOW_LABELS.get(found.how, found.how)
                ])
        if new_lines:
            self._emails_view.appendPlainText("\n".join(new_lines))
        for email, reason in result.rejected:
            if email not in self._rejected:
                self._rejected[email] = reason
                self._append_row(self._rejected_table, [email, reason])

        note = result.error or (result.final_url if result.final_url.rstrip("/") != result.site.rstrip("/") else "")
        row = self._append_row(self._sites_table, [
            result.site,
            STATUS_LABELS.get(result.status, result.status),
            str(len(result.emails)),
            str(result.pages),
            f"{result.elapsed:.1f}s",
            VIA_LABELS.get(result.via, result.via),
            note,
        ])
        status_item = self._sites_table.item(row, 1)
        status_item.setForeground(QColor(STATUS_COLORS.get(result.status, theme.TEXT)))
        if result.status in STATUS_TIPS:
            status_item.setToolTip(STATUS_TIPS[result.status])
        self._sites_table.item(row, 5).setToolTip(VIA_TIPS.get(result.via, ""))
        for column in (2, 3, 4):
            self._sites_table.item(row, column).setTextAlignment(
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
            )
        if write_log and result.log:
            self._log.appendPlainText("\n".join(["", f"── {result.site}", *result.log]))

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
            ("Sites", len(self._results), None),
            ("Emails", len(self._emails), theme.SUCCESS if self._emails else None),
            ("Found", counts[FOUND], theme.SUCCESS if counts[FOUND] else None),
        ]
        for status in (FORM_ONLY, EMPTY, PARKED, BLOCKED, FAILED):
            if counts[status]:
                items.append((STATUS_LABELS[status], counts[status], STATUS_COLORS[status]))
        if self._rejected:
            items.append(("Rejected", len(self._rejected), theme.WARNING))
        self._stats.setText(stats_html(items))
        has_emails = bool(self._emails)
        self._copy_button.setEnabled(has_emails)
        self._send_button.setEnabled(has_emails)
        self._copy_details_button.setEnabled(has_emails)
        self._copy_sites_button.setEnabled(bool(self._results))
        retryable = sum(counts[status] for status in RETRYABLE)
        self._retry_button.setEnabled(retryable > 0 and self._task is None)
        self._tabs.setTabText(3, f"Rejected ({len(self._rejected)})" if self._rejected else "Rejected")

    # ------------------------------------------------------------- clipboard
    def _copy_emails(self) -> None:
        if self._emails:
            QGuiApplication.clipboard().setText("\n".join(self._emails))
            flash_button(self._copy_button, "Copied ✓")

    def _copy_details(self) -> None:
        lines = ["Email\tSite\tFound on\tHow"]
        for email, (found, site) in self._emails.items():
            lines.append(f"{email}\t{site}\t{found.page}\t{HOW_LABELS.get(found.how, found.how)}")
        QGuiApplication.clipboard().setText("\n".join(lines))
        flash_button(self._copy_details_button, "Copied ✓")

    def _copy_sites(self) -> None:
        lines = ["Site\tStatus\tEmails\tPages\tTime\tVia\tNote\tAddresses"]
        for result in self._results:
            addresses = ", ".join(found.email for found in result.emails)
            lines.append(
                f"{result.site}\t{STATUS_LABELS.get(result.status, result.status)}\t"
                f"{len(result.emails)}\t{result.pages}\t{result.elapsed:.1f}\t"
                f"{VIA_LABELS.get(result.via, result.via)}\t{result.error or result.final_url}\t{addresses}"
            )
        QGuiApplication.clipboard().setText("\n".join(lines))
        flash_button(self._copy_sites_button, "Copied ✓")

    def receive_text(self, text: str) -> None:
        if self._task is not None:
            QMessageBox.information(self, EmailScraperTool.name, "Wait for the current scan to finish first.")
            return
        self._sites.setPlainText(text)
        self._sites.setFocus()

    def _retry_failed(self) -> None:
        failed = [result.site for result in self._results if result.status in RETRYABLE]
        if failed:
            self._sites.setPlainText("\n".join(failed))
            self._sites.setFocus()

    # ---------------------------------------------------------------- session
    def _save_session(self) -> None:
        self._save_timer.stop()
        if not self._persist_session:
            return
        data = {
            "sites": self._sites.toPlainText(),
            "total": self._total,
            "results": [
                {
                    "site": r.site, "status": r.status, "final_url": r.final_url,
                    "pages": r.pages, "error": r.error, "elapsed": round(r.elapsed, 2),
                    "language": r.language, "contact_form": r.contact_form, "via": r.via,
                    "emails": [[f.email, f.page, f.how] for f in r.emails],
                    "rejected": [list(item) for item in r.rejected],
                }
                for r in self._results
            ],
        }
        try:
            self._session_doc.save(data)
        except OSError:
            log.exception("Could not save the scraper session")

    def _restore_session(self) -> None:
        data = self._session_doc.load()
        sites = data.get("sites")
        if isinstance(sites, str):
            self._sites.setPlainText(sites)
        try:
            for item in data.get("results", []):
                result = SiteResult(
                    site=item["site"], status=item["status"], final_url=item.get("final_url", ""),
                    emails=[FoundEmail(*email) for email in item.get("emails", [])],
                    rejected=[tuple(pair) for pair in item.get("rejected", [])],
                    pages=int(item.get("pages", 0)), error=item.get("error", ""),
                    elapsed=float(item.get("elapsed", 0)), language=item.get("language", ""),
                    contact_form=item.get("contact_form", ""), via=item.get("via", "http"),
                )
                self._add_result(result, write_log=False)
        except (KeyError, TypeError, ValueError):
            log.exception("Ignoring a damaged scraper session")
        self._total = int(data.get("total", len(self._results)) or 0)
        if self._results:
            self._log.appendPlainText(
                f"Restored the last scan: {len(self._results)} of {self._total} sites. "
                "Detailed logs are kept only while the app is open."
            )
        self._update_stats()

    def save_state(self) -> None:
        """Called when the window closes: stop a running scan and keep the results."""
        if self._task is not None:
            self._task.cancel()
        self._save_session()

    def load_demo(self) -> None:
        """Show sample results without network access or saving (CI screenshots)."""
        self._persist_session = False
        self._sites.setPlainText(
            "acme.example\nfirma.example\nshop.example\nform.example\nparked.example\n"
            "guarded.example\nold-site.example"
        )
        self._clear_results()
        self._total = 7
        samples = [
            SiteResult("https://acme.example", FOUND, "https://acme.example/", [
                FoundEmail("info@acme.example", "https://acme.example/", "structured"),
                FoundEmail("sales@acme.example", "https://acme.example/contact", "link"),
            ], [("noreply@acme.example", "Automated sender (noreply)")], 3, "", 2.4, "en"),
            SiteResult("https://firma.example", FOUND, "https://firma.example/", [
                FoundEmail("buero@firma.example", "https://firma.example/impressum", "text"),
            ], [], 2, "", 1.9, "de"),
            SiteResult("https://shop.example", FOUND, "https://www.shop.example/tr/", [
                FoundEmail("destek@shop.example", "https://www.shop.example/tr/iletisim", "protected"),
            ], [("a8f3k2m9x7q1w5e4z@shop.example", "Random-looking username")], 5, "", 4.1, "tr",
                via="browser"),
            SiteResult("https://form.example", FORM_ONLY, "https://form.example/", [], [], 6,
                       "Only a contact form (https://form.example/contact)", 5.2, "en"),
            SiteResult("https://parked.example", PARKED, "https://parked.example/", [], [], 1,
                       "Parked or for-sale domain", 0.8),
            SiteResult("https://guarded.example", BLOCKED, "https://guarded.example/", [], [], 1,
                       "Bot protection or captcha (HTTP 503)", 1.1),
            SiteResult("https://old-site.example", FAILED, error="SSL error", pages=3, elapsed=1.2),
        ]
        for result in samples:
            self._add_result(result, write_log=False)
        self._update_stats()


def _duration(seconds: float) -> str:
    seconds = int(seconds)
    if seconds < 60:
        return f"{seconds}s"
    minutes, seconds = divmod(seconds, 60)
    if minutes < 60:
        return f"{minutes}m {seconds:02d}s"
    hours, minutes = divmod(minutes, 60)
    return f"{hours}h {minutes:02d}m"
