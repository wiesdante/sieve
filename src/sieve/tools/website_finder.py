"""Website Finder: search company names on DuckDuckGo and keep each company's own
website, never its social media, directory or marketplace pages.

Layout: options on top, then Companies | Results side by side, like Email Scraper.
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
from sieve.core.website_finder import (
    DIRECT_COOLDOWN,
    FAILED,
    FOUND,
    NO_SITE,
    PROXY_COOLDOWN,
    RATE_LIMITED,
    STATUSES,
    UNSURE,
    BrowserSearcher,
    Candidate,
    Connections,
    FinderResult,
    FinderSettings,
    FinderSummary,
    RunStatus,
    find_websites,
    parse_block_rules,
    parse_companies,
)
from sieve.proxy import ProxyPool
from sieve.storage import JsonDocument
from sieve.tools.base import Tool
from sieve.tools.email_scraper import BROWSER_POOL_LIMIT, LOG_LINE_LIMIT, _duration, _editor, _table
from sieve.ui import theme
from sieve.ui.routing import SendToButton, notify_finished
from sieve.ui.tasks import BackgroundTask, run_in_background
from sieve.ui.website_rules import WebsiteRulesDialog, load_block_lists
from sieve.ui.widgets import (
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

TOOL_ID = "website_finder"
SESSION_DOCUMENT = "website_finder_session"
WORKER_CHOICES = (1, 3, 5, 10, 20)
STATUS_LABELS = {
    FOUND: "Found", UNSURE: "Unsure", NO_SITE: "No website", RATE_LIMITED: "Rate limited", FAILED: "Failed",
}
STATUS_COLORS = {
    FOUND: theme.SUCCESS, UNSURE: theme.ACCENT_HOVER, NO_SITE: theme.TEXT_MUTED,
    RATE_LIMITED: theme.WARNING, FAILED: theme.DANGER,
}
STATUS_TIPS = {
    FOUND: "The company's own website.",
    UNSURE: "A close candidate that may be the company's site. It is not in the Websites list; "
            "check it yourself.",
    NO_SITE: "DuckDuckGo answered, but none of the results is the company's own website.",
    RATE_LIMITED: "DuckDuckGo kept asking to slow down. Retry later or with more proxies.",
    FAILED: "The search could not be made.",
}
VERDICT_LABELS = {"found": "Website", "unsure": "Unsure", "skipped": "Skipped"}
RETRYABLE = (RATE_LIMITED, FAILED)


class WebsiteFinderTool(Tool):
    id = TOOL_ID
    name = "Website Finder"
    description = "Finds companies' own websites by searching their names on DuckDuckGo."
    category = "Scraping"
    icon = "search"

    def self_check(self) -> None:
        import bs4  # noqa: F401

        from sieve.core.browser import ensure_browser_support

        ensure_browser_support()

    def create_widget(self, context: AppContext) -> QWidget:
        return WebsiteFinderPage(context)


def run_job(
    companies: list[str],
    settings: FinderSettings,
    workers: int,
    pool: ProxyPool | None,
    status: RunStatus,
    progress=None,
    cancelled=None,
) -> FinderSummary:
    from sieve.core.browser import BrowserFetcher, BrowserPool

    proxies = pool.proxies if pool else None
    # DuckDuckGo turns plain HTTP clients down; searches go through the real browser.
    browsers = BrowserPool(size=max(1, min(BROWSER_POOL_LIMIT, workers, len(proxies or [None]))),
                           uses_proxies=bool(proxies))

    def searcher_for(proxy):
        return BrowserSearcher(BrowserFetcher(browsers, proxy.for_playwright() if proxy else None))

    status.set("Starting the browser...")
    try:
        connections = Connections(proxies, searcher_for, status)
        return find_websites(companies, connections, settings, workers, progress=progress, cancelled=cancelled)
    finally:
        browsers.close()


class WebsiteFinderPage(ToolPage):
    def __init__(self, context: AppContext) -> None:
        super().__init__(WebsiteFinderTool.name, WebsiteFinderTool.description)
        self._context = context
        self._prefs = context.tool_settings(TOOL_ID)
        self._session_doc = JsonDocument(SESSION_DOCUMENT)
        self._task: BackgroundTask | None = None
        self._persist_session = True
        self._status = RunStatus()
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
        self._splitter.addWidget(self._build_companies_panel())
        self._splitter.addWidget(self._build_results_panel())
        self._splitter.setSizes([4, 7])
        saved = self._prefs.get("splitter")
        if isinstance(saved, str) and saved:
            self._splitter.restoreState(QByteArray.fromBase64(saved.encode("ascii")))
        self._splitter.splitterMoved.connect(self._save_splitter)
        self.content.addWidget(self._splitter, 1)

        copy_shortcut = QShortcut(QKeySequence("Ctrl+Shift+C"), self)
        copy_shortcut.activated.connect(self._copy_websites)

        self._refresh_proxy_option()
        self._restore_session()

    def _reset_state(self) -> None:
        self._results: dict[str, FinderResult] = {}
        #: company order as entered, for the table and copies
        self._order: list[str] = []
        self._total = 0
        self._started_at = 0.0

    # --------------------------------------------------------------- toolbar
    def _build_toolbar(self) -> QFrame:
        bar = QFrame()
        bar.setObjectName("Toolbar")
        row = QHBoxLayout(bar)
        row.setContentsMargins(14, 8, 14, 8)
        row.setSpacing(14)

        rules = compact_button("Rules...", "Which sites never count as a company's website, and your block lists.")
        rules.clicked.connect(lambda: WebsiteRulesDialog(self._prefs, self._context.save_settings, self).exec())

        self._use_proxies = QCheckBox("Use proxies")
        self._use_proxies.setChecked(bool(self._prefs.get("use_proxies", True)))
        self._use_proxies.toggled.connect(self._save_options)

        self._workers = QComboBox()
        for count in WORKER_CHOICES:
            self._workers.addItem(f"{count} at a time", count)
        index = self._workers.findData(int(self._prefs.get("workers", 5)))
        self._workers.setCurrentIndex(index if index >= 0 else self._workers.findData(5))
        self._workers.setToolTip(
            "How many searches run at the same time. Never more than the number of proxies,\n"
            "and each proxy rests between searches."
        )
        self._workers.currentIndexChanged.connect(self._save_options)

        for widget in (rules, self._use_proxies):
            widget.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
            row.addWidget(widget)
        row.addStretch(1)
        row.addWidget(self._workers)
        return bar

    def _refresh_proxy_option(self) -> None:
        pool = self._context.proxy_pool()
        if pool:
            self._use_proxies.setEnabled(True)
            self._use_proxies.setText(f"Use proxies ({len(pool)})")
            self._use_proxies.setToolTip("Spread the searches over the proxies from Settings.")
        else:
            self._use_proxies.setEnabled(False)
            self._use_proxies.setText("Use proxies")
            reason = "turned off" if self._context.settings.proxies else "empty"
            self._use_proxies.setToolTip(f"The proxy list in Settings is {reason}.")
        self._use_proxies.blockSignals(True)
        self._use_proxies.setChecked(bool(pool) and bool(self._prefs.get("use_proxies", True)))
        self._use_proxies.blockSignals(False)
        self._update_pace_hint()

    def _update_pace_hint(self) -> None:
        pool = self._context.proxy_pool() if self._use_proxies.isChecked() else None
        if pool:
            per_minute = int(60 / PROXY_COOLDOWN * len(pool))
            text = (f"{len(pool)} proxies · about {per_minute} searches a minute at most; "
                    "each proxy rests between searches.")
        else:
            text = (f"No proxies: one search every {DIRECT_COOLDOWN:.0f}+ seconds. Searches run in your "
                    "browser (Chrome or Edge), out of sight; proxies help with long lists.")
        self._pace_hint.setText(text)

    def showEvent(self, event) -> None:  # noqa: N802 (Qt override)
        self._refresh_proxy_option()
        super().showEvent(event)

    def _save_options(self) -> None:
        self._prefs.update(workers=self._workers.currentData())
        if self._use_proxies.isEnabled():  # an unavailable list must not overwrite the choice
            self._prefs["use_proxies"] = self._use_proxies.isChecked()
        self._context.save_settings()
        if hasattr(self, "_pace_hint"):
            self._update_pace_hint()

    def _save_splitter(self) -> None:
        self._prefs["splitter"] = bytes(self._splitter.saveState().toBase64()).decode("ascii")
        self._context.save_settings()

    # ------------------------------------------------------------- companies
    def _build_companies_panel(self) -> QFrame:
        panel, body, header = titled_panel("Companies")
        self._companies_info = muted_label(wrap=False)
        header.addWidget(self._companies_info)
        header.addStretch(1)
        paste = compact_button("Paste", "Replace the list with the clipboard contents.")
        clear = compact_button("Clear", "Clear the list.")
        paste.clicked.connect(self._paste_companies)
        clear.clicked.connect(lambda: self._companies.clear())
        header.addWidget(paste)
        header.addWidget(clear)

        self._companies = _editor("One company name per line, e.g.\nAselsan\nBird Aerosystems Ltd.")
        self._companies.textChanged.connect(self._update_companies_info)
        body.addWidget(self._companies, 1)

        self._pace_hint = muted_label()
        body.addWidget(self._pace_hint)

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
        self._stop_button.setToolTip("Finish the searches in progress and stop.")
        self._stop_button.setEnabled(False)
        self._stop_button.clicked.connect(self._stop)
        footer.addWidget(self._start_button, 1)
        footer.addWidget(self._stop_button)
        body.addLayout(footer)
        self._update_companies_info()
        return panel

    def _update_companies_info(self) -> None:
        count = len(parse_companies(self._companies.toPlainText()))
        self._companies_info.setText(f"· {format_number(count)} companies")

    def _paste_companies(self) -> None:
        text = QGuiApplication.clipboard().text()
        if text:
            self._companies.setPlainText(text)

    # --------------------------------------------------------------- results
    def _build_results_panel(self) -> QFrame:
        panel, body, header = titled_panel("Results")
        header.addStretch(1)
        self._copy_button = primary_button("Copy websites")
        self._copy_button.setToolTip("Copy the websites found, one per line (Ctrl+Shift+C).")
        self._copy_button.clicked.connect(self._copy_websites)
        header.addWidget(self._copy_button)

        self._stats = QLabel()
        self._stats.setObjectName("Stats")
        self._stats.setTextFormat(Qt.TextFormat.RichText)
        body.addWidget(self._stats)

        self._tabs = QTabWidget()
        self._tabs.setUsesScrollButtons(False)
        self._websites_view = _editor("Websites will appear here as searches finish.", read_only=True)
        self._table = _table(["Company", "Status", "Website", "Match", "#", "Title", "Note"], stretch=0)
        self._checked_table = _table(["Company", "#", "Verdict", "Address", "Reason"], stretch=0)
        self._log = _editor("", read_only=True)
        self._log.setMaximumBlockCount(LOG_LINE_LIMIT)
        self._tabs.addTab(self._websites_view, "Websites")
        self._tabs.addTab(self._table, "Companies")
        self._tabs.addTab(self._checked_table, "Checked results")
        self._tabs.addTab(self._log, "Log")
        body.addWidget(self._tabs, 1)

        footer = QHBoxLayout()
        footer.setSpacing(6)
        self._copy_table_button = compact_button(
            "Copy table", "Copy every company with its website, status and match (pastes into Excel)."
        )
        self._retry_button = compact_button(
            "Retry failed", "Put the companies whose search was rate limited or failed back into the list."
        )
        self._copy_table_button.clicked.connect(self._copy_table)
        self._retry_button.clicked.connect(self._retry_failed)
        footer.addWidget(self._copy_table_button)
        self._send_button = SendToButton(TOOL_ID, self._websites_text)
        footer.addWidget(self._send_button)
        footer.addWidget(self._retry_button)
        footer.addStretch(1)
        body.addLayout(footer)
        return panel

    # ------------------------------------------------------------------- run
    def _settings(self) -> FinderSettings:
        settings = FinderSettings.from_dict(self._prefs.get("rules", {}))
        settings.region = ""  # all regions
        settings.block = parse_block_rules(load_block_lists().text)
        return settings

    def _start(self) -> None:
        if self._task is not None:
            return
        companies = parse_companies(self._companies.toPlainText())
        if not companies:
            self._companies.setFocus()
            flash_button(self._start_button, "Add companies first")
            return
        if self._results:
            answer = QMessageBox.question(
                self, WebsiteFinderTool.name, "Starting a new search clears the current results. Continue?"
            )
            if answer != QMessageBox.StandardButton.Yes:
                return
        pool = self._context.proxy_pool() if self._use_proxies.isChecked() else None
        settings = self._settings()
        workers = self._workers.currentData()

        self._clear_results()
        self._order = companies
        self._total = len(companies)
        self._started_at = time.monotonic()
        self._set_running(True)
        self._log.appendPlainText(
            f"Started {time.strftime('%Y-%m-%d %H:%M:%S')} · {len(companies)} companies"
            + (f" · {len(pool)} proxies" if pool else " · no proxies")
            + (f" · {len(settings.block)} block rules" if settings.block else "")
        )
        self._status = RunStatus()
        self._task = run_in_background(
            run_job, companies, settings, workers, pool, self._status,
            on_success=self._on_done, on_error=self._on_error, on_progress=self._on_company_done,
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
        self._companies.setReadOnly(running)
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
        text = f"{format_number(done)} / {format_number(self._total)} companies · {_duration(elapsed)}"
        if done and done < self._total:
            text += f" · about {_duration(elapsed / done * (self._total - done))} left"
        now = self._status.text if self._task is not None else ""
        self._progress_label.setText(text + (f"\n{now}" if now else ""))

    def _on_company_done(self, result: FinderResult, total: int) -> None:
        self._add_result(result)
        self._progress.setValue(int(len(self._results) * 100 / max(total, 1)))
        self._update_progress_label()
        self._update_stats()
        self._save_timer.start()

    def _on_done(self, summary: FinderSummary) -> None:
        self._task = None
        self._set_running(False)
        elapsed = time.monotonic() - self._started_at
        word = "Stopped" if summary.stopped else "Finished"
        found = sum(1 for result in summary.results if result.status == FOUND)
        self._log.appendPlainText(
            f"{word} after {_duration(elapsed)} · websites for {found} of {len(summary.results)} companies"
        )
        self._rebuild_views()  # in the order the companies were entered
        self._save_session()
        notify_finished(self)

    def _on_error(self, exc: Exception) -> None:
        self._task = None
        self._set_running(False)
        log.error("Website search failed", exc_info=exc)
        self._save_session()
        QMessageBox.critical(self, WebsiteFinderTool.name, f"An unexpected error occurred:\n{exc}")

    # --------------------------------------------------------- result views
    def _clear_results(self) -> None:
        self._reset_state()
        self._websites_view.clear()
        self._log.clear()
        self._table.setRowCount(0)
        self._checked_table.setRowCount(0)
        self._update_stats()

    def _ordered(self) -> list[FinderResult]:
        position = {company: index for index, company in enumerate(self._order)}
        return sorted(self._results.values(), key=lambda r: position.get(r.company, len(position)))

    def _websites(self) -> list[str]:
        websites: list[str] = []
        for result in self._ordered():
            if result.status == FOUND and result.website not in websites:
                websites.append(result.website)
        return websites

    def _owners(self) -> dict[str, list[str]]:
        owners: dict[str, list[str]] = {}
        for result in self._ordered():
            if result.status == FOUND:
                owners.setdefault(result.website, []).append(result.company)
        return owners

    def _add_result(self, result: FinderResult, write_log: bool = True) -> None:
        self._results[result.company] = result
        if result.company not in self._order:
            self._order.append(result.company)
        if result.status == FOUND and result.website not in self._websites_view.toPlainText().splitlines():
            self._websites_view.appendPlainText(result.website)
        self._append_result_rows(result)
        if write_log and result.log:
            self._log.appendPlainText("\n".join(["", f"── {result.company}", *result.log]))

    def _append_result_rows(self, result: FinderResult, owners: dict[str, list[str]] | None = None) -> None:
        owners = owners if owners is not None else self._owners()
        others = [c for c in owners.get(result.website, []) if c != result.company] if result.website else []
        note = result.error
        if others:
            note = "Same website as: " + ", ".join(others)
        elif result.found_url and result.found_url.rstrip("/") != result.website.rstrip("/"):
            note = f"Found as {result.found_url}"
        row = self._append_row(self._table, [
            result.company,
            STATUS_LABELS.get(result.status, result.status),
            result.website,
            result.match,
            str(result.rank) if result.rank else "",
            result.title,
            note,
        ])
        status_item = self._table.item(row, 1)
        status_item.setForeground(QColor(STATUS_COLORS.get(result.status, theme.TEXT)))
        status_item.setToolTip(STATUS_TIPS.get(result.status, ""))
        if others:
            self._table.item(row, 6).setForeground(QColor(theme.WARNING))
        self._table.item(row, 4).setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        for candidate in result.candidates:
            self._append_candidate(result.company, candidate)

    def _append_candidate(self, company: str, candidate: Candidate) -> None:
        row = self._append_row(self._checked_table, [
            company, str(candidate.rank), VERDICT_LABELS.get(candidate.verdict, candidate.verdict),
            candidate.url, candidate.reason,
        ])
        color = {"found": theme.SUCCESS, "unsure": theme.ACCENT_HOVER}.get(candidate.verdict, theme.TEXT_MUTED)
        self._checked_table.item(row, 2).setForeground(QColor(color))

    def _rebuild_views(self) -> None:
        self._table.setRowCount(0)
        self._checked_table.setRowCount(0)
        owners = self._owners()
        for result in self._ordered():
            self._append_result_rows(result, owners)
        self._websites_view.setPlainText("\n".join(self._websites()))
        self._update_stats()

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
        for result in self._results.values():
            counts[result.status] = counts.get(result.status, 0) + 1
        websites = self._websites()
        items = [
            ("Companies", len(self._results), None),
            ("Websites", len(websites), theme.SUCCESS if websites else None),
        ]
        for status in (UNSURE, NO_SITE, RATE_LIMITED, FAILED):
            if counts[status]:
                items.append((STATUS_LABELS[status], counts[status], STATUS_COLORS[status]))
        self._stats.setText(stats_html(items))
        self._copy_button.setEnabled(bool(websites))
        self._send_button.setEnabled(bool(websites))
        self._copy_table_button.setEnabled(bool(self._results))
        retryable = counts[RATE_LIMITED] + counts[FAILED]
        self._retry_button.setEnabled(retryable > 0 and self._task is None)

    # ------------------------------------------------------------- clipboard
    def _websites_text(self) -> str:
        return "\n".join(self._websites())

    def _copy_websites(self) -> None:
        text = self._websites_text()
        if text:
            QGuiApplication.clipboard().setText(text)
            flash_button(self._copy_button, "Copied ✓")

    def _copy_table(self) -> None:
        lines = ["Company\tStatus\tWebsite\tMatch\tResult #\tFound as\tTitle\tNote"]
        for result in self._ordered():
            lines.append("\t".join([
                result.company, STATUS_LABELS.get(result.status, result.status), result.website,
                result.match, str(result.rank or ""), result.found_url, result.title, result.error,
            ]))
        QGuiApplication.clipboard().setText("\n".join(lines))
        flash_button(self._copy_table_button, "Copied ✓")

    def receive_text(self, text: str) -> None:
        if self._task is not None:
            QMessageBox.information(self, WebsiteFinderTool.name, "Wait for the current search to finish first.")
            return
        self._companies.setPlainText(text)
        self._companies.setFocus()

    def _retry_failed(self) -> None:
        failed = [result.company for result in self._ordered() if result.status in RETRYABLE]
        if failed:
            self._companies.setPlainText("\n".join(failed))
            self._companies.setFocus()

    # ---------------------------------------------------------------- session
    def _save_session(self) -> None:
        self._save_timer.stop()
        if not self._persist_session:
            return
        data = {
            "companies": self._companies.toPlainText(),
            "order": self._order,
            "total": self._total,
            "results": [
                {
                    "company": r.company, "status": r.status, "website": r.website, "found_url": r.found_url,
                    "title": r.title, "rank": r.rank, "match": r.match, "error": r.error,
                    "searches": r.searches, "elapsed": round(r.elapsed, 2),
                    "candidates": [[c.url, c.title, c.rank, c.verdict, c.reason] for c in r.candidates],
                }
                for r in self._ordered()
            ],
        }
        try:
            self._session_doc.save(data)
        except OSError:
            log.exception("Could not save the website finder session")

    def _restore_session(self) -> None:
        data = self._session_doc.load()
        companies = data.get("companies")
        if isinstance(companies, str):
            self._companies.setPlainText(companies)
        order = data.get("order")
        self._order = [str(name) for name in order] if isinstance(order, list) else []
        try:
            for item in data.get("results", []):
                result = FinderResult(
                    company=item["company"], status=item["status"], website=item.get("website", ""),
                    found_url=item.get("found_url", ""), title=item.get("title", ""),
                    rank=int(item.get("rank", 0)), match=item.get("match", ""), error=item.get("error", ""),
                    searches=int(item.get("searches", 0)), elapsed=float(item.get("elapsed", 0)),
                    candidates=[Candidate(*candidate) for candidate in item.get("candidates", [])],
                )
                self._results[result.company] = result
        except (KeyError, TypeError, ValueError):
            log.exception("Ignoring a damaged website finder session")
        self._total = int(data.get("total", len(self._results)) or 0)
        self._rebuild_views()
        if self._results:
            self._log.appendPlainText(
                f"Restored the last search: {len(self._results)} of {self._total} companies. "
                "Detailed logs are kept only while the app is open."
            )

    def save_state(self) -> None:
        """Called when the window closes: stop a running search and keep the results."""
        if self._task is not None:
            self._task.cancel()
        self._save_session()

    def load_demo(self) -> None:
        """Show sample results without network access or saving (CI screenshots)."""
        self._persist_session = False
        names = ["Bird Aerosystems Ltd.", "Aselsan A.Ş.", "Acme Savunma Sanayi", "Excalibur Army",
                 "Nobody Trading Co.", "Busy Example GmbH"]
        self._companies.setPlainText("\n".join(names))
        self._clear_results()
        self._order = names
        self._total = len(names)
        samples = [
            FinderResult(names[0], FOUND, "https://www.birdaero.com/", "https://www.birdaero.com/products/",
                         "AMIPS - Bird Aerosystems", 3, "Domain matches the name", [
                             Candidate("https://www.linkedin.com/company/bird", "Bird | LinkedIn", 1, "skipped",
                                       "Social media and video"),
                             Candidate("https://www.kompass.com/c/bird/", "BIRD - Kompass", 2, "skipped",
                                       "Business directories and company data"),
                             Candidate("https://www.birdaero.com/products/", "AMIPS", 3, "found",
                                       "Domain matches the name"),
                         ]),
            FinderResult(names[1], FOUND, "https://www.aselsan.com/", "https://www.aselsan.com/tr", "ASELSAN", 1,
                         "Domain matches the name"),
            FinderResult(names[2], UNSURE, "https://www.acmetools.com/", "https://www.acmetools.com/",
                         "Acme Tools", 2, "Domain is close to the name"),
            FinderResult(names[3], FOUND, "https://www.excaliburarmy.cz/", "https://www.excaliburarmy.cz/en",
                         "Excalibur Army", 1, "Domain matches the name"),
            FinderResult(names[4], NO_SITE, error="No result is the company's own site"),
            FinderResult(names[5], RATE_LIMITED, error="DuckDuckGo asked to slow down (HTTP 202)"),
        ]
        for result in samples:
            self._results[result.company] = result
        self._rebuild_views()
