"""Link & Email Extractor: collect web links or email addresses from PDFs or text.

Layout: mode and options on top, then Source | Output side by side. The source
is either a list of PDF files (drag and drop or "Add PDFs...") or pasted text.
"""

from __future__ import annotations

import logging
import tempfile
from pathlib import Path

from PySide6.QtCore import QByteArray, Qt
from PySide6.QtGui import QGuiApplication, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QSizePolicy,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from sieve.context import AppContext
from sieve.core.email_filter import EmailFilter
from sieve.core.link_extractor import (
    EMAILS,
    LINK,
    LINKS,
    ExtractCancelledError,
    ExtractOptions,
    ExtractResult,
    PdfBackendMissingError,
    ensure_pdf_backend,
    extract_from_pdfs,
    extract_from_text,
)
from sieve.tools.base import Tool
from sieve.ui import theme
from sieve.ui.email_rules import EmailRulesDialog, load_filter
from sieve.ui.routing import SendToButton, notify_finished
from sieve.ui.tasks import BackgroundTask, run_in_background
from sieve.ui.widgets import (
    FileDropList,
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

TOOL_ID = "link_extractor"
PDF_TAB, TEXT_TAB = 0, 1
DETAILS_LIMIT = 5_000
MODE_LABELS = {LINKS: "links", EMAILS: "emails"}


class LinkExtractorTool(Tool):
    id = TOOL_ID
    name = "Link & Email Extractor"
    description = "Collects web links or email addresses from PDF files or pasted text."
    category = "Extract"
    icon = "link"

    def self_check(self) -> None:
        ensure_pdf_backend()
        import dns.resolver  # noqa: F401

    def create_widget(self, context: AppContext) -> QWidget:
        return LinkExtractorPage(context)


def run_job(
    files: list[Path],
    text: str | None,
    options: ExtractOptions,
    email_filter: EmailFilter | None = None,
    progress=None,
    cancelled=None,
) -> ExtractResult:
    if files:
        return extract_from_pdfs(
            files, options, progress=progress, cancelled=cancelled, email_filter=email_filter
        )
    return extract_from_text(text or "", options, email_filter)


def _editor(placeholder: str, read_only: bool = False) -> QPlainTextEdit:
    editor = QPlainTextEdit()
    editor.setObjectName("Editor")
    editor.setPlaceholderText(placeholder)
    editor.setReadOnly(read_only)
    editor.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
    return editor


class LinkExtractorPage(ToolPage):
    def __init__(self, context: AppContext) -> None:
        super().__init__(LinkExtractorTool.name, LinkExtractorTool.description)
        self._context = context
        self._prefs = context.tool_settings(TOOL_ID)
        self._task: BackgroundTask | None = None
        self._result: ExtractResult | None = None

        self.content.addWidget(self._build_toolbar())

        self._splitter = QSplitter(Qt.Orientation.Horizontal)
        self._splitter.setChildrenCollapsible(False)
        self._splitter.setHandleWidth(12)
        self._splitter.addWidget(self._build_source_panel())
        self._splitter.addWidget(self._build_output_panel())
        self._splitter.setSizes([1, 1])
        saved = self._prefs.get("splitter")
        if isinstance(saved, str) and saved:
            self._splitter.restoreState(QByteArray.fromBase64(saved.encode("ascii")))
        self._splitter.splitterMoved.connect(self._save_splitter)
        self.content.addWidget(self._splitter, 1)

        for keys in ("Ctrl+Return", "Ctrl+Enter"):
            shortcut = QShortcut(QKeySequence(keys), self)
            shortcut.activated.connect(self._run)
        copy_shortcut = QShortcut(QKeySequence("Ctrl+Shift+C"), self)
        copy_shortcut.activated.connect(self._copy_output)

        self._apply_mode(self._prefs.get("mode", LINKS), save=False)
        self._show_result(None)

    # --------------------------------------------------------------- toolbar
    def _build_toolbar(self) -> QFrame:
        bar = QFrame()
        bar.setObjectName("Toolbar")
        row = QHBoxLayout(bar)
        row.setContentsMargins(14, 8, 14, 8)
        row.setSpacing(14)

        self._mode_control = SegmentedControl(
            [
                (LINKS, "Links", "Collect web links (clickable links and addresses in the text)."),
                (EMAILS, "Emails", "Collect email addresses (mailto: links and addresses in the text)."),
            ],
            self,
        )
        self._mode_control.changed.connect(self._apply_mode)
        row.addLayout(self._mode_control.layout)

        defaults = ExtractOptions()
        self._bare_domains = QCheckBox("Include bare domains")
        self._bare_domains.setToolTip(
            'Also collect "example.com" written without http:// or www.\n'
            "File names such as report.pdf are ignored."
        )
        self._bare_domains.setChecked(
            bool(self._prefs.get("include_bare_domains", defaults.include_bare_domains))
        )
        self._domains_only = QCheckBox("Domains only")
        self._domains_only.setChecked(bool(self._prefs.get("domains_only", defaults.domains_only)))
        self._filter_junk = QCheckBox("Filter junk")
        self._filter_junk.setToolTip(
            "Emails mode: remove placeholders, no-reply, disposable, tracking and image-name\n"
            "addresses. Removed addresses are listed under Rejected."
        )
        self._filter_junk.setChecked(bool(self._prefs.get("filter_junk", True)))
        for box in (self._bare_domains, self._domains_only, self._filter_junk):
            box.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
            box.toggled.connect(self._save_options)
            row.addWidget(box)
        self._rules_button = compact_button("Rules...", "Edit which addresses count as junk.")
        self._rules_button.clicked.connect(lambda: EmailRulesDialog(self).exec())
        row.addWidget(self._rules_button)
        row.addStretch(1)
        self._mode_hint = muted_label(wrap=False)
        row.addWidget(self._mode_hint)
        return bar

    def _apply_mode(self, mode: str, save: bool = True) -> None:
        if mode not in (LINKS, EMAILS):
            mode = LINKS
        self._mode = mode
        self._mode_control.set_current(mode)
        self._bare_domains.setVisible(mode == LINKS)
        self._filter_junk.setVisible(mode == EMAILS)
        self._rules_button.setVisible(mode == EMAILS)
        if mode == LINKS:
            self._domains_only.setToolTip('Output only the site of each link, e.g. "example.com".')
            self._mode_hint.setText("Duplicates are removed; http/https and www. count as the same.")
            self._run_button.setText("Extract links")
        else:
            self._domains_only.setToolTip(
                'Output only the part after "@", e.g. "example.com".'
            )
            self._mode_hint.setText("Duplicates are removed, ignoring letter case.")
            self._run_button.setText("Extract emails")
        if save:
            self._prefs["mode"] = mode
            self._context.save_settings()

    def _options(self) -> ExtractOptions:
        return ExtractOptions(
            mode=self._mode,
            include_bare_domains=self._bare_domains.isChecked(),
            domains_only=self._domains_only.isChecked(),
        )

    def _save_options(self) -> None:
        self._prefs.update(
            include_bare_domains=self._bare_domains.isChecked(),
            domains_only=self._domains_only.isChecked(),
            filter_junk=self._filter_junk.isChecked(),
        )
        self._context.save_settings()

    def _save_splitter(self) -> None:
        self._prefs["splitter"] = bytes(self._splitter.saveState().toBase64()).decode("ascii")
        self._context.save_settings()

    # ---------------------------------------------------------------- source
    def _build_source_panel(self) -> QFrame:
        panel, body, header = titled_panel("Source")
        self._source_info = muted_label(wrap=False)
        header.addWidget(self._source_info)
        header.addStretch(1)

        self._source_tabs = QTabWidget()
        self._source_tabs.setUsesScrollButtons(False)

        files_tab = QWidget()
        files_layout = QVBoxLayout(files_tab)
        files_layout.setContentsMargins(10, 10, 10, 10)
        files_layout.setSpacing(8)
        self._files = FileDropList((".pdf",))
        self._files.files_added.connect(self._on_files_changed)
        files_layout.addWidget(self._files, 1)
        file_buttons = QHBoxLayout()
        file_buttons.setSpacing(6)
        add = compact_button("Add PDFs...", "Choose one or more PDF files.")
        remove = compact_button("Remove", "Remove the selected files from the list.")
        clear = compact_button("Clear", "Remove all files from the list.")
        add.clicked.connect(self._choose_files)
        remove.clicked.connect(self._remove_selected)
        clear.clicked.connect(self._clear_files)
        file_buttons.addWidget(add)
        file_buttons.addWidget(remove)
        file_buttons.addWidget(clear)
        file_buttons.addStretch(1)
        file_buttons.addWidget(muted_label("or drop PDF files on the list", wrap=False))
        files_layout.addLayout(file_buttons)
        self._source_tabs.addTab(files_tab, "PDF files")

        self._text = _editor("Paste any text here...")
        self._text.textChanged.connect(self._update_source_info)
        self._source_tabs.addTab(self._text, "Text")
        self._source_tabs.setCurrentIndex(int(self._prefs.get("source_tab", PDF_TAB)) % 2)
        self._source_tabs.currentChanged.connect(self._on_source_tab_changed)
        body.addWidget(self._source_tabs, 1)

        footer = QHBoxLayout()
        footer.setSpacing(8)
        self._run_button = primary_button("Extract links")
        self._run_button.setToolTip("Ctrl+Enter")
        self._run_button.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._run_button.clicked.connect(self._run)
        self._progress = QProgressBar()
        self._progress.setRange(0, 100)
        self._progress.hide()
        self._cancel_button = QPushButton("Cancel")
        self._cancel_button.hide()
        self._cancel_button.clicked.connect(self._cancel)
        footer.addWidget(self._run_button, 1)
        footer.addWidget(self._progress, 1)
        footer.addWidget(self._cancel_button)
        body.addLayout(footer)
        self._update_source_info()
        return panel

    def _files_mode(self) -> bool:
        return self._source_tabs.currentIndex() == PDF_TAB

    def _on_source_tab_changed(self, index: int) -> None:
        self._prefs["source_tab"] = index
        self._context.save_settings()
        self._update_source_info()

    def _on_files_changed(self) -> None:
        self._source_tabs.setCurrentIndex(PDF_TAB)
        self._update_source_info()

    def _update_source_info(self) -> None:
        if self._files_mode():
            count = self._files.count()
            self._source_info.setText(f"· {count} file" + ("" if count == 1 else "s"))
        else:
            lines = self._text.blockCount() if self._text.toPlainText() else 0
            self._source_info.setText(f"· {format_number(lines)} lines")

    def _choose_files(self) -> None:
        files, _ = QFileDialog.getOpenFileNames(
            self, "Add PDF files", self._prefs.get("last_dir", ""), "PDF files (*.pdf)"
        )
        if files:
            paths = [Path(f) for f in files]
            self._prefs["last_dir"] = str(paths[0].parent)
            self._context.save_settings()
            self._files.add_files(paths)

    def _remove_selected(self) -> None:
        self._files.remove_selected()
        self._update_source_info()

    def _clear_files(self) -> None:
        self._files.clear()
        self._update_source_info()

    # ---------------------------------------------------------------- output
    def _build_output_panel(self) -> QFrame:
        panel, body, header = titled_panel("Output")
        header.addStretch(1)
        self._copy_button = primary_button("Copy")
        self._copy_button.setToolTip("Copy the result, one per line (Ctrl+Shift+C).")
        self._copy_button.clicked.connect(self._copy_output)
        header.addWidget(self._copy_button)

        self._stats = muted_label(wrap=False)
        self._stats.setObjectName("Stats")
        self._stats.setTextFormat(Qt.TextFormat.RichText)
        body.addWidget(self._stats)

        self._result_tabs = QTabWidget()
        self._result_tabs.setUsesScrollButtons(False)
        self._output = _editor("The result will appear here, one per line.", read_only=True)
        self._details = QTableWidget(0, 4)
        self._details.setHorizontalHeaderLabels(["Found", "Source", "Page", "From"])
        self._details.verticalHeader().hide()
        self._details.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._details.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        details_header = self._details.horizontalHeader()
        details_header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        for column in (1, 2, 3):
            details_header.setSectionResizeMode(column, QHeaderView.ResizeMode.ResizeToContents)
        self._problems = _editor("", read_only=True)
        self._result_tabs.addTab(self._output, "Result")
        self._result_tabs.addTab(self._details, "Details")
        self._result_tabs.addTab(self._problems, "Problems")
        self._rejected = QTableWidget(0, 2)
        self._rejected.setHorizontalHeaderLabels(["Address", "Reason"])
        self._rejected.verticalHeader().hide()
        self._rejected.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._rejected.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self._rejected.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self._result_tabs.addTab(self._rejected, "Rejected")
        self._result_tabs.setTabVisible(3, False)
        self._result_tabs.setTabToolTip(1, "Where each item was first found.")
        self._result_tabs.setTabVisible(2, False)
        body.addWidget(self._result_tabs, 1)

        footer = QHBoxLayout()
        footer.setSpacing(6)
        self._copy_details_button = compact_button(
            "Copy details", "Copy the Details table as tab-separated text (pastes into Excel)."
        )
        self._copy_details_button.clicked.connect(self._copy_details)
        footer.addWidget(self._copy_details_button)
        self._send_button = SendToButton(TOOL_ID, self._result_text)
        footer.addWidget(self._send_button)
        footer.addStretch(1)
        self._auto_copy = QCheckBox("Auto-copy")
        self._auto_copy.setToolTip("Copy the result to the clipboard as soon as it is ready.")
        self._auto_copy.setChecked(bool(self._prefs.get("auto_copy", False)))
        self._auto_copy.toggled.connect(self._save_auto_copy)
        footer.addWidget(self._auto_copy)
        body.addLayout(footer)
        return panel

    def _save_auto_copy(self, checked: bool) -> None:
        self._prefs["auto_copy"] = checked
        self._context.save_settings()

    # ------------------------------------------------------------------- run
    def _run(self) -> None:
        if self._task is not None:
            return
        files = self._files.paths() if self._files_mode() else []
        text = None if self._files_mode() else self._text.toPlainText()
        if self._files_mode() and not files:
            flash_button(self._run_button, "Add PDF files first")
            return
        if not self._files_mode() and not (text or "").strip():
            self._text.setFocus()
            flash_button(self._run_button, "Paste some text first")
            return
        email_filter = (
            load_filter() if self._mode == EMAILS and self._filter_junk.isChecked() else None
        )
        self._set_running(True)
        self._task = run_in_background(
            run_job,
            files,
            text,
            self._options(),
            email_filter,
            on_success=self._on_done,
            on_error=self._on_error,
            on_progress=self._on_progress,
        )

    def _cancel(self) -> None:
        if self._task:
            self._task.cancel()

    def _set_running(self, running: bool) -> None:
        self._run_button.setVisible(not running)
        self._progress.setVisible(running)
        self._cancel_button.setVisible(running)
        self._progress.setValue(0)

    def _on_progress(self, done: int, total: int) -> None:
        if total:
            self._progress.setValue(int(done * 100 / total))

    def _on_error(self, exc: Exception) -> None:
        self._task = None
        self._set_running(False)
        if isinstance(exc, ExtractCancelledError):
            return
        if isinstance(exc, PdfBackendMissingError):
            QMessageBox.critical(self, LinkExtractorTool.name, str(exc))
            return
        log.error("Extraction failed", exc_info=exc)
        QMessageBox.critical(self, LinkExtractorTool.name, f"An unexpected error occurred:\n{exc}")

    def _on_done(self, result: ExtractResult) -> None:
        self._task = None
        self._set_running(False)
        self._result = result
        self._show_result(result)
        notify_finished(self)
        if self._auto_copy.isChecked() and result.links:
            self._copy_output()

    def _show_result(self, result: ExtractResult | None) -> None:
        has_items = bool(result and result.links)
        self._copy_button.setEnabled(has_items)
        self._send_button.setEnabled(has_items)
        self._copy_details_button.setEnabled(has_items)
        if result is None:
            self._stats.setText(stats_html([("Found", 0, None), ("Unique", 0, None)]))
            self._output.clear()
            self._details.setRowCount(0)
            self._rejected.setRowCount(0)
            self._result_tabs.setTabVisible(2, False)
            self._result_tabs.setTabVisible(3, False)
            return

        items = []
        if result.files:
            items += [("Files", result.files, None), ("Pages", result.pages, None)]
        items += [
            ("Found", result.total_found, None),
            ("Unique", len(result.links), theme.SUCCESS if result.links else None),
        ]
        if result.rejected:
            items.append(("Rejected", len(result.rejected), theme.WARNING))
        if result.errors:
            items.append(("Problems", len(result.errors), theme.DANGER))
        self._stats.setText(stats_html(items))
        self._output.setPlainText("\n".join(result.lines))
        if not result.links:
            self._output.setPlaceholderText(f"No {MODE_LABELS[self._mode]} were found.")

        rows = result.links[:DETAILS_LIMIT]
        self._details.setRowCount(len(rows))
        for row, item in enumerate(rows):
            page = QTableWidgetItem("" if item.page is None else str(item.page))
            page.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            kind = "Clickable link" if item.kind == LINK else "Text"
            for column, cell in enumerate(
                (QTableWidgetItem(item.value), QTableWidgetItem(item.source), page, QTableWidgetItem(kind))
            ):
                self._details.setItem(row, column, cell)

        self._problems.setPlainText("\n".join(f"{name}: {message}" for name, message in result.errors))
        self._result_tabs.setTabVisible(2, bool(result.errors))
        self._result_tabs.setTabText(2, f"Problems ({len(result.errors)})")
        self._rejected.setRowCount(len(result.rejected))
        for row, (email, reason) in enumerate(result.rejected):
            self._rejected.setItem(row, 0, QTableWidgetItem(email))
            self._rejected.setItem(row, 1, QTableWidgetItem(reason))
        self._result_tabs.setTabVisible(3, bool(result.rejected))
        self._result_tabs.setTabText(3, f"Rejected ({len(result.rejected)})")
        self._result_tabs.setCurrentIndex(0)

    def _result_text(self) -> str:
        return "\n".join(self._result.lines) if self._result else ""

    def receive_text(self, text: str) -> None:
        self._source_tabs.setCurrentIndex(TEXT_TAB)
        self._text.setPlainText(text)
        self._text.setFocus()

    def _copy_output(self) -> None:
        if not self._result or not self._result.links:
            return
        QGuiApplication.clipboard().setText("\n".join(self._result.lines))
        flash_button(self._copy_button, "Copied ✓")

    def _copy_details(self) -> None:
        if not self._result or not self._result.links:
            return
        lines = ["Found\tSource\tPage\tFrom"]
        for item in self._result.links:
            page = "" if item.page is None else str(item.page)
            kind = "Clickable link" if item.kind == LINK else "Text"
            lines.append(f"{item.value}\t{item.source}\t{page}\t{kind}")
        QGuiApplication.clipboard().setText("\n".join(lines))
        flash_button(self._copy_details_button, "Copied ✓")

    def load_demo(self) -> None:
        """Run on a generated sample PDF (used for CI screenshots)."""
        import pymupdf

        folder = Path(tempfile.mkdtemp(prefix="sieve-demo-"))
        samples = {
            "brochure.pdf": [
                ("Visit www.acme.example or shop.io. Mail sales@acme.example", "https://acme.example/offer"),
                ("Docs: https://docs.acme.example/start. See report.pdf", "mailto:ceo@acme.example"),
            ],
            "partners.pdf": [
                ("Partner: https://partner.example and http://www.acme.example/", None),
            ],
        }
        paths = []
        for name, pages in samples.items():
            doc = pymupdf.open()
            for text, uri in pages:
                page = doc.new_page()
                page.insert_text((72, 72), text, fontsize=11)
                if uri:
                    rect = pymupdf.Rect(72, 90, 300, 105)
                    page.insert_link({"kind": pymupdf.LINK_URI, "from": rect, "uri": uri})
            path = folder / name
            doc.save(str(path))
            doc.close()
            paths.append(path)
        self._files.clear()
        self._files.add_files(paths)
        self._apply_mode(LINKS, save=False)
        self._on_done(run_job(paths, None, self._options()))
