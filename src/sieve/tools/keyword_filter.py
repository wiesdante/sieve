"""Keyword Filter: keep or drop lines with a saved blacklist or whitelist.

Layout: options on top, then Input | Keywords | Output side by side. Both
keyword lists are saved automatically to the user's data folder, so they
survive restarts and updates.
"""

from __future__ import annotations

import logging

from PySide6.QtCore import QByteArray, Qt, QTimer
from PySide6.QtGui import QColor, QGuiApplication, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
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
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QWidget,
)

from sieve.context import AppContext
from sieve.core.keyword_filter import (
    BLACKLIST,
    WHITELIST,
    FilterCancelledError,
    FilterOptions,
    FilterResult,
    filter_lines,
    parse_keywords,
)
from sieve.storage import JsonDocument
from sieve.tools.base import Tool
from sieve.ui import theme
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

TOOL_ID = "keyword_filter"
LISTS_DOCUMENT = "keyword_lists"
MODE_HINTS = {
    BLACKLIST: "Removes every line that contains a keyword.",
    WHITELIST: "Keeps only the lines that contain a keyword.",
}


class KeywordFilterTool(Tool):
    id = TOOL_ID
    name = "Keyword Filter"
    description = "Filters lines with a saved blacklist or whitelist of keywords."
    category = "Text"
    icon = "filter"

    def create_widget(self, context: AppContext) -> QWidget:
        return KeywordFilterPage(context)


def run_job(
    text: str, keywords: list[str], options: FilterOptions, progress=None, cancelled=None
) -> FilterResult:
    return filter_lines(
        text.splitlines(), keywords, options, progress=progress, cancelled=cancelled
    )


class KeywordFilterPage(ToolPage):
    def __init__(self, context: AppContext) -> None:
        super().__init__(KeywordFilterTool.name, KeywordFilterTool.description)
        self._context = context
        self._prefs = context.tool_settings(TOOL_ID)
        self._lists_doc = JsonDocument(LISTS_DOCUMENT)
        self._task: BackgroundTask | None = None
        self._result: FilterResult | None = None
        self._persist_lists = True

        self._save_timer = QTimer(self)
        self._save_timer.setSingleShot(True)
        self._save_timer.setInterval(400)
        self._save_timer.timeout.connect(self.save_state)

        self.content.addWidget(self._build_toolbar())

        self._splitter = QSplitter(Qt.Orientation.Horizontal)
        self._splitter.setChildrenCollapsible(False)
        self._splitter.setHandleWidth(12)
        self._splitter.addWidget(self._build_input_panel())
        self._splitter.addWidget(self._build_keywords_panel())
        self._splitter.addWidget(self._build_output_panel())
        self._splitter.setSizes([10, 7, 10])
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

        self._load_lists()
        self._apply_mode(self._prefs.get("mode", BLACKLIST), save=False)
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
                (BLACKLIST, "Blacklist", MODE_HINTS[BLACKLIST]),
                (WHITELIST, "Whitelist", MODE_HINTS[WHITELIST]),
            ],
            self,
        )
        self._mode_control.changed.connect(self._apply_mode)
        row.addLayout(self._mode_control.layout)

        defaults = FilterOptions()

        def checkbox(key: str, text: str, tooltip: str) -> QCheckBox:
            box = QCheckBox(text)
            box.setToolTip(tooltip)
            box.setChecked(bool(self._prefs.get(key, getattr(defaults, key))))
            box.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
            box.toggled.connect(self._save_options)
            row.addWidget(box)
            return box

        self._ignore_case = checkbox(
            "ignore_case", "Ignore case", '"cat" also matches "CAT". Turkish İ/i are matched correctly.'
        )
        self._whole_word = checkbox(
            "whole_word",
            "Whole words",
            'Off: "cat" also matches "category".\nOn: "cat" only matches the word "cat".',
        )
        self._skip_empty = checkbox(
            "skip_empty", "Skip empty lines", "Drop empty lines in both modes."
        )
        row.addStretch(1)
        self._mode_hint = muted_label(wrap=False)
        row.addWidget(self._mode_hint)
        return bar

    def _apply_mode(self, mode: str, save: bool = True) -> None:
        if mode not in (BLACKLIST, WHITELIST):
            mode = BLACKLIST
        self._mode = mode
        self._mode_control.set_current(mode)
        self._lists_stack.setCurrentWidget(self._list_editors[mode])
        self._keywords_title.setText("Blacklist" if mode == BLACKLIST else "Whitelist")
        self._mode_hint.setText(MODE_HINTS[mode])
        self._update_keyword_count()
        if save:
            self._prefs["mode"] = mode
            self._context.save_settings()

    def _options(self) -> FilterOptions:
        return FilterOptions(
            mode=self._mode,
            ignore_case=self._ignore_case.isChecked(),
            whole_word=self._whole_word.isChecked(),
            skip_empty=self._skip_empty.isChecked(),
        )

    def _save_options(self) -> None:
        self._prefs.update(
            ignore_case=self._ignore_case.isChecked(),
            whole_word=self._whole_word.isChecked(),
            skip_empty=self._skip_empty.isChecked(),
        )
        self._context.save_settings()

    def _save_splitter(self) -> None:
        self._prefs["splitter"] = bytes(self._splitter.saveState().toBase64()).decode("ascii")
        self._context.save_settings()

    # ----------------------------------------------------------------- input
    def _build_input_panel(self) -> QFrame:
        panel, body, header = titled_panel("Input")
        self._input_info = muted_label(wrap=False)
        header.addWidget(self._input_info)
        header.addStretch(1)
        paste = compact_button("Paste", "Replace the input with the clipboard contents.")
        clear = compact_button("Clear", "Clear the input.")
        paste.clicked.connect(self._paste_from_clipboard)
        clear.clicked.connect(self._clear_input)
        header.addWidget(paste)
        header.addWidget(clear)

        self._input = QPlainTextEdit()
        self._input.setObjectName("Editor")
        self._input.setPlaceholderText("Paste the text to filter here...")
        self._input.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self._input.textChanged.connect(self._update_input_info)
        body.addWidget(self._input, 1)

        footer = QHBoxLayout()
        footer.setSpacing(8)
        self._run_button = primary_button("Filter lines")
        self._run_button.setToolTip("Ctrl+Enter")
        self._run_button.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._run_button.clicked.connect(self._run)
        self._paste_run_button = QPushButton("Paste && run")
        self._paste_run_button.setToolTip("Paste from the clipboard and filter in one click.")
        self._paste_run_button.clicked.connect(self._paste_and_run)
        self._progress = QProgressBar()
        self._progress.setRange(0, 100)
        self._progress.hide()
        self._cancel_button = QPushButton("Cancel")
        self._cancel_button.hide()
        self._cancel_button.clicked.connect(self._cancel)
        footer.addWidget(self._run_button, 1)
        footer.addWidget(self._paste_run_button)
        footer.addWidget(self._progress, 1)
        footer.addWidget(self._cancel_button)
        body.addLayout(footer)
        self._update_input_info()
        return panel

    def _update_input_info(self) -> None:
        lines = self._input.blockCount() if self._input.toPlainText() else 0
        self._input_info.setText(f"· {format_number(lines)} lines")

    def _paste_from_clipboard(self) -> bool:
        text = QGuiApplication.clipboard().text()
        if not text:
            return False
        self._input.setPlainText(text)
        return True

    def _clear_input(self) -> None:
        self._input.clear()
        self._input.setFocus()

    def _paste_and_run(self) -> None:
        if self._paste_from_clipboard():
            self._run()
        else:
            flash_button(self._paste_run_button, "Clipboard is empty")

    # -------------------------------------------------------------- keywords
    def _build_keywords_panel(self) -> QFrame:
        panel, body, header = titled_panel("Blacklist")
        self._keywords_title = panel.findChild(QLabel, "PanelTitle")
        self._keyword_count = muted_label(wrap=False)
        header.addWidget(self._keyword_count)
        header.addStretch(1)

        self._lists_stack = QStackedWidget()
        self._list_editors: dict[str, QPlainTextEdit] = {}
        for mode in (BLACKLIST, WHITELIST):
            editor = QPlainTextEdit()
            editor.setObjectName("Editor")
            editor.setPlaceholderText("One keyword per line")
            editor.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
            editor.textChanged.connect(self._on_list_edited)
            self._list_editors[mode] = editor
            self._lists_stack.addWidget(editor)
        body.addWidget(self._lists_stack, 1)

        footer = QHBoxLayout()
        self._saved_label = muted_label("Saved automatically", wrap=False)
        footer.addWidget(self._saved_label)
        footer.addStretch(1)
        body.addLayout(footer)
        return panel

    def _current_keywords(self) -> list[str]:
        return parse_keywords(self._list_editors[self._mode].toPlainText())

    def _update_keyword_count(self) -> None:
        count = len(self._current_keywords())
        self._keyword_count.setText(f"· {format_number(count)} keywords")

    def _load_lists(self) -> None:
        data = self._lists_doc.load()
        for mode, editor in self._list_editors.items():
            value = data.get(mode, "")
            editor.blockSignals(True)
            editor.setPlainText(value if isinstance(value, str) else "")
            editor.blockSignals(False)

    def _on_list_edited(self) -> None:
        self._update_keyword_count()
        if self._persist_lists:
            self._saved_label.setText("Saving...")
            self._save_timer.start()

    def save_state(self) -> None:
        """Write both keyword lists to disk (also called when the window closes)."""
        self._save_timer.stop()
        if not self._persist_lists:
            return
        data = {mode: editor.toPlainText() for mode, editor in self._list_editors.items()}
        try:
            self._lists_doc.save(data)
        except OSError:
            log.exception("Could not save keyword lists")
            self._saved_label.setText("Could not save, see log")
            self._saved_label.setStyleSheet(f"color: {theme.DANGER};")
            return
        self._saved_label.setText("Saved ✓")
        self._saved_label.setStyleSheet("")

    # ---------------------------------------------------------------- output
    def _build_output_panel(self) -> QFrame:
        panel, body, header = titled_panel("Output")
        header.addStretch(1)
        self._copy_button = primary_button("Copy")
        self._copy_button.setToolTip("Copy the kept lines to the clipboard (Ctrl+Shift+C).")
        self._copy_button.clicked.connect(self._copy_output)
        header.addWidget(self._copy_button)

        self._stats = QLabel()
        self._stats.setObjectName("Stats")
        self._stats.setTextFormat(Qt.TextFormat.RichText)
        body.addWidget(self._stats)

        self._result_tabs = QTabWidget()
        self._output = self._read_only_editor("The kept lines will appear here.")
        self._removed = self._read_only_editor("Lines that were filtered out appear here.")
        self._hits_table = QTableWidget(0, 2)
        self._hits_table.setHorizontalHeaderLabels(["Keyword", "Lines"])
        self._hits_table.verticalHeader().hide()
        self._hits_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._hits_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        hits_header = self._hits_table.horizontalHeader()
        hits_header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        hits_header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self._result_tabs.setUsesScrollButtons(False)
        self._result_tabs.addTab(self._output, "Result")
        self._result_tabs.addTab(self._removed, "Removed")
        self._result_tabs.addTab(self._hits_table, "Hits")
        body.addWidget(self._result_tabs, 1)

        footer = QHBoxLayout()
        footer.setSpacing(6)
        self._to_input_button = compact_button(
            "Use as input", "Move the result to the input to filter it again."
        )
        self._copy_removed_button = compact_button(
            "Copy removed", "Copy the lines that were filtered out."
        )
        self._to_input_button.clicked.connect(self._use_as_input)
        self._copy_removed_button.clicked.connect(self._copy_removed)
        footer.addWidget(self._to_input_button)
        footer.addWidget(self._copy_removed_button)
        footer.addStretch(1)
        self._auto_copy = QCheckBox("Auto-copy")
        self._auto_copy.setToolTip("Copy the result to the clipboard as soon as it is ready.")
        self._auto_copy.setChecked(bool(self._prefs.get("auto_copy", False)))
        self._auto_copy.toggled.connect(self._save_auto_copy)
        footer.addWidget(self._auto_copy)
        body.addLayout(footer)
        return panel

    @staticmethod
    def _read_only_editor(placeholder: str) -> QPlainTextEdit:
        editor = QPlainTextEdit()
        editor.setObjectName("Editor")
        editor.setReadOnly(True)
        editor.setPlaceholderText(placeholder)
        editor.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        return editor

    def _save_auto_copy(self, checked: bool) -> None:
        self._prefs["auto_copy"] = checked
        self._context.save_settings()

    # ------------------------------------------------------------------- run
    def _run(self) -> None:
        if self._task is not None:
            return
        text = self._input.toPlainText()
        if not text.strip():
            self._input.setFocus()
            flash_button(self._run_button, "Paste some text first")
            return
        keywords = self._current_keywords()
        if not keywords:
            self._list_editors[self._mode].setFocus()
            flash_button(self._run_button, "Add keywords first")
            return
        self._set_running(True)
        self._task = run_in_background(
            run_job,
            text,
            keywords,
            self._options(),
            on_success=self._on_done,
            on_error=self._on_error,
            on_progress=self._on_progress,
        )

    def _cancel(self) -> None:
        if self._task:
            self._task.cancel()

    def _set_running(self, running: bool) -> None:
        self._run_button.setVisible(not running)
        self._paste_run_button.setVisible(not running)
        self._progress.setVisible(running)
        self._cancel_button.setVisible(running)
        self._progress.setValue(0)

    def _on_progress(self, done: int, total: int) -> None:
        if total:
            self._progress.setValue(int(done * 100 / total))

    def _on_error(self, exc: Exception) -> None:
        self._task = None
        self._set_running(False)
        if isinstance(exc, FilterCancelledError):
            return
        log.error("Keyword filtering failed", exc_info=exc)
        QMessageBox.critical(self, "Keyword Filter", f"An unexpected error occurred:\n{exc}")

    def _on_done(self, result: FilterResult) -> None:
        self._task = None
        self._set_running(False)
        self._result = result
        self._show_result(result)
        if self._auto_copy.isChecked():
            self._copy_output()

    def _show_result(self, result: FilterResult | None) -> None:
        for button in (self._copy_button, self._to_input_button, self._copy_removed_button):
            button.setEnabled(result is not None)
        if result is None:
            self._stats.setText(stats_html([("Total", 0, None), ("Kept", 0, None), ("Removed", 0, None)]))
            self._output.clear()
            self._removed.clear()
            self._hits_table.setRowCount(0)
            return

        self._stats.setText(
            stats_html([
                ("Total", result.total, None),
                ("Kept", len(result.kept), theme.SUCCESS),
                ("Removed", len(result.removed), theme.WARNING if result.removed else None),
            ])
            + f"&nbsp;&nbsp;·&nbsp;&nbsp;{result.retention:.1f}% kept"
        )
        self._output.setPlainText("\n".join(result.kept))
        self._removed.setPlainText("\n".join(result.removed))

        muted = QColor(theme.TEXT_MUTED)
        self._hits_table.setRowCount(len(result.keyword_hits))
        for row, (keyword, count) in enumerate(result.keyword_hits):
            keyword_item = QTableWidgetItem(keyword)
            count_item = QTableWidgetItem(format_number(count))
            count_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            if count == 0:
                keyword_item.setForeground(muted)
                count_item.setForeground(muted)
                keyword_item.setToolTip("This keyword did not match any line.")
            self._hits_table.setItem(row, 0, keyword_item)
            self._hits_table.setItem(row, 1, count_item)

        self._result_tabs.setTabText(1, f"Removed ({format_number(len(result.removed))})")
        unused = sum(1 for _, count in result.keyword_hits if count == 0)
        self._result_tabs.setTabToolTip(
            2,
            f"How many lines each keyword matched. {unused} keywords matched nothing."
            if unused else "How many lines each keyword matched.",
        )
        self._result_tabs.setCurrentIndex(0)

    def _copy_output(self) -> None:
        if not self._result:
            return
        QGuiApplication.clipboard().setText("\n".join(self._result.kept))
        flash_button(self._copy_button, "Copied ✓")

    def _copy_removed(self) -> None:
        if not self._result:
            return
        if not self._result.removed:
            flash_button(self._copy_removed_button, "Nothing removed")
            return
        QGuiApplication.clipboard().setText("\n".join(self._result.removed))
        flash_button(self._copy_removed_button, "Copied ✓")

    def _use_as_input(self) -> None:
        if self._result:
            self._input.setPlainText("\n".join(self._result.kept))
            self._input.setFocus()

    def load_demo(self) -> None:
        """Fill the page with sample data without touching the saved lists (CI screenshots)."""
        self._persist_lists = False
        self._list_editors[BLACKLIST].setPlainText("casino\nloan\nfree money\nunused keyword")
        self._list_editors[WHITELIST].setPlainText("shoes\nİstanbul")
        self._input.setPlainText("\n".join([
            "Running shoes - 20% off",
            "Online casino bonus",
            "Leather shoes, İstanbul store",
            "Get a fast loan today",
            "Garden furniture set",
            "FREE MONEY click here",
            "Kitchen knives",
        ]))
        self._apply_mode(BLACKLIST, save=False)
        self._on_done(run_job(self._input.toPlainText(), self._current_keywords(), self._options()))
