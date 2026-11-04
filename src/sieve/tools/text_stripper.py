"""Text Stripper: remove saved phrases (labels, prefixes, boilerplate) from every line.

Layout: options on top, then Input | Phrases | Output side by side. The phrase
list is saved automatically and survives restarts and updates. Spaces are
shown in the phrase editor because a trailing space is part of a phrase.
"""

from __future__ import annotations

import logging

from PySide6.QtCore import QByteArray, Qt, QTimer
from PySide6.QtGui import QColor, QGuiApplication, QKeySequence, QShortcut, QTextOption
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
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
    QWidget,
)

from sieve.context import AppContext
from sieve.core.presets import PresetLists
from sieve.core.text_stripper import (
    PatternError,
    StripCancelledError,
    StripOptions,
    StripResult,
    parse_phrases,
    strip_lines,
)
from sieve.storage import JsonDocument
from sieve.tools.base import Tool
from sieve.ui import theme
from sieve.ui.presets import PresetBar
from sieve.ui.tasks import BackgroundTask, run_in_background
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

TOOL_ID = "text_stripper"
PHRASES_DOCUMENT = "strip_phrases"


class TextStripperTool(Tool):
    id = TOOL_ID
    name = "Text Stripper"
    description = "Removes saved phrases such as labels and prefixes from every line."
    category = "Text"
    icon = "eraser"

    def create_widget(self, context: AppContext) -> QWidget:
        return TextStripperPage(context)


def run_job(
    text: str, phrases: list[str], options: StripOptions, progress=None, cancelled=None
) -> StripResult:
    return strip_lines(text.splitlines(), phrases, options, progress=progress, cancelled=cancelled)


def _editor(placeholder: str, read_only: bool = False) -> QPlainTextEdit:
    editor = QPlainTextEdit()
    editor.setObjectName("Editor")
    editor.setPlaceholderText(placeholder)
    editor.setReadOnly(read_only)
    editor.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
    return editor


class TextStripperPage(ToolPage):
    def __init__(self, context: AppContext) -> None:
        super().__init__(TextStripperTool.name, TextStripperTool.description)
        self._context = context
        self._prefs = context.tool_settings(TOOL_ID)
        self._phrases_doc = JsonDocument(PHRASES_DOCUMENT)
        self._task: BackgroundTask | None = None
        self._result: StripResult | None = None
        self._persist_phrases = True

        self._save_timer = QTimer(self)
        self._save_timer.setSingleShot(True)
        self._save_timer.setInterval(400)
        self._save_timer.timeout.connect(self.save_state)

        self.content.addWidget(self._build_toolbar())

        self._splitter = QSplitter(Qt.Orientation.Horizontal)
        self._splitter.setChildrenCollapsible(False)
        self._splitter.setHandleWidth(12)
        self._splitter.addWidget(self._build_input_panel())
        self._splitter.addWidget(self._build_phrases_panel())
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

        self._load_phrases()
        self._show_result(None)

    # --------------------------------------------------------------- toolbar
    def _build_toolbar(self) -> QFrame:
        bar = QFrame()
        bar.setObjectName("Toolbar")
        row = QHBoxLayout(bar)
        row.setContentsMargins(14, 8, 14, 8)
        row.setSpacing(14)
        defaults = StripOptions()

        def checkbox(key: str, text: str, tooltip: str) -> QCheckBox:
            box = QCheckBox(text)
            box.setToolTip(tooltip)
            box.setChecked(bool(self._prefs.get(key, getattr(defaults, key))))
            box.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
            box.toggled.connect(self._save_options)
            row.addWidget(box)
            return box

        self._ignore_case = checkbox(
            "ignore_case",
            "Ignore case",
            '"Email: " also removes "EMAIL: ". Turkish İ/i are matched correctly.',
        )
        self._trim_lines = checkbox(
            "trim_lines",
            "Trim lines",
            "Remove spaces left at the start and end of each line after stripping.",
        )
        self._remove_empty = checkbox(
            "remove_empty",
            "Drop empty lines",
            "Remove lines that are empty once the phrases have been stripped.",
        )
        self._regex = checkbox(
            "regex",
            "Regex",
            "Treat every phrase as a regular expression, e.g. \\(.*?\\) removes anything in brackets.\n"
            "Without Regex, phrases are matched literally, longest first.",
        )
        self._regex.toggled.connect(self._update_mode_hint)
        row.addStretch(1)
        self._mode_hint = muted_label(wrap=False)
        row.addWidget(self._mode_hint)
        self._update_mode_hint()
        return bar

    def _update_mode_hint(self) -> None:
        self._mode_hint.setText(
            "Patterns are tried in the order written."
            if self._regex.isChecked()
            else "Every match is removed, longest phrase first."
        )

    def _options(self) -> StripOptions:
        return StripOptions(
            ignore_case=self._ignore_case.isChecked(),
            trim_lines=self._trim_lines.isChecked(),
            remove_empty=self._remove_empty.isChecked(),
            regex=self._regex.isChecked(),
        )

    def _save_options(self) -> None:
        options = self._options()
        self._prefs.update(
            ignore_case=options.ignore_case,
            trim_lines=options.trim_lines,
            remove_empty=options.remove_empty,
            regex=options.regex,
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

        self._input = _editor("Paste the text to clean here...")
        self._input.textChanged.connect(self._update_input_info)
        body.addWidget(self._input, 1)

        footer = QHBoxLayout()
        footer.setSpacing(8)
        self._run_button = primary_button("Strip phrases")
        self._run_button.setToolTip("Ctrl+Enter")
        self._run_button.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._run_button.clicked.connect(self._run)
        self._paste_run_button = QPushButton("Paste && run")
        self._paste_run_button.setToolTip("Paste from the clipboard and strip in one click.")
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

    # --------------------------------------------------------------- phrases
    def _build_phrases_panel(self) -> QFrame:
        panel, body, header = titled_panel("Phrases")
        self._phrase_count = muted_label(wrap=False)
        header.addWidget(self._phrase_count)
        header.addStretch(1)

        self._presets = PresetLists()
        self._preset_bar = PresetBar("list")
        self._preset_bar.selected.connect(self._on_preset_selected)
        self._preset_bar.changed.connect(self._schedule_save)
        body.addWidget(self._preset_bar)

        self._phrases = _editor("One phrase per line, e.g.\nEmail: \nPhone: ")
        # Make spaces visible: "Email: " and "Email:" strip differently.
        option = self._phrases.document().defaultTextOption()
        option.setFlags(option.flags() | QTextOption.Flag.ShowTabsAndSpaces)
        self._phrases.document().setDefaultTextOption(option)
        self._phrases.textChanged.connect(self._on_phrases_edited)
        body.addWidget(self._phrases, 1)

        hint = muted_label("Spaces show as dots. A trailing space is part of the phrase.")
        body.addWidget(hint)
        self._saved_label = muted_label("Saved automatically", wrap=False)
        body.addWidget(self._saved_label)
        return panel

    def _current_phrases(self) -> list[str]:
        return parse_phrases(self._phrases.toPlainText())

    def _update_phrase_count(self) -> None:
        self._phrase_count.setText(f"· {format_number(len(self._current_phrases()))} phrases")

    def _load_phrases(self) -> None:
        data = self._phrases_doc.load()
        # Older versions stored a single list under "phrases".
        self._presets = PresetLists.from_data(data if "lists" in data else data.get("phrases"))
        self._preset_bar.set_presets(self._presets)
        self._show_current_preset()

    def _show_current_preset(self) -> None:
        self._phrases.blockSignals(True)
        self._phrases.setPlainText(self._presets.text)
        self._phrases.blockSignals(False)
        self._update_phrase_count()

    def _on_preset_selected(self, _name: str) -> None:
        self._show_current_preset()

    def _on_phrases_edited(self) -> None:
        self._presets.lists[self._presets.current] = self._phrases.toPlainText()
        self._update_phrase_count()
        self._schedule_save()

    def _schedule_save(self) -> None:
        if self._persist_phrases:
            self._saved_label.setText("Saving...")
            self._save_timer.start()

    def save_state(self) -> None:
        """Write the phrase list to disk (also called when the window closes)."""
        self._save_timer.stop()
        if not self._persist_phrases:
            return
        try:
            self._phrases_doc.save({"version": 2, **self._presets.to_data()})
        except OSError:
            log.exception("Could not save strip phrases")
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
        self._copy_button.setToolTip("Copy the cleaned text to the clipboard (Ctrl+Shift+C).")
        self._copy_button.clicked.connect(self._copy_output)
        header.addWidget(self._copy_button)

        self._stats = muted_label(wrap=False)
        self._stats.setObjectName("Stats")
        self._stats.setTextFormat(Qt.TextFormat.RichText)
        body.addWidget(self._stats)

        self._result_tabs = QTabWidget()
        self._result_tabs.setUsesScrollButtons(False)
        self._output = _editor("The cleaned text will appear here.", read_only=True)
        self._hits_table = QTableWidget(0, 2)
        self._hits_table.setHorizontalHeaderLabels(["Phrase", "Removed"])
        self._hits_table.verticalHeader().hide()
        self._hits_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._hits_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        hits_header = self._hits_table.horizontalHeader()
        hits_header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        hits_header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self._result_tabs.addTab(self._output, "Result")
        self._result_tabs.addTab(self._hits_table, "Hits")
        self._result_tabs.setTabToolTip(1, "How many times each phrase was removed.")
        body.addWidget(self._result_tabs, 1)

        footer = QHBoxLayout()
        footer.setSpacing(6)
        self._to_input_button = compact_button(
            "Use as input", "Move the result to the input to process it again."
        )
        self._to_input_button.clicked.connect(self._use_as_input)
        footer.addWidget(self._to_input_button)
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
        text = self._input.toPlainText()
        if not text.strip():
            self._input.setFocus()
            flash_button(self._run_button, "Paste some text first")
            return
        phrases = self._current_phrases()
        if not phrases:
            self._phrases.setFocus()
            flash_button(self._run_button, "Add phrases first")
            return
        self._set_running(True)
        self._task = run_in_background(
            run_job,
            text,
            phrases,
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
        if isinstance(exc, StripCancelledError):
            return
        if isinstance(exc, PatternError):
            details = "\n".join(f"• {pattern}  —  {message}" for pattern, message in exc.errors[:10])
            QMessageBox.warning(
                self, "Text Stripper", f"Some phrases are not valid regular expressions:\n\n{details}"
            )
            return
        log.error("Text stripping failed", exc_info=exc)
        QMessageBox.critical(self, "Text Stripper", f"An unexpected error occurred:\n{exc}")

    def _on_done(self, result: StripResult) -> None:
        self._task = None
        self._set_running(False)
        self._result = result
        self._show_result(result)
        if self._auto_copy.isChecked():
            self._copy_output()

    def _show_result(self, result: StripResult | None) -> None:
        self._copy_button.setEnabled(result is not None)
        self._to_input_button.setEnabled(result is not None)
        if result is None:
            self._stats.setText(stats_html([("Lines", 0, None), ("Changed", 0, None), ("Removed", 0, None)]))
            self._output.clear()
            self._hits_table.setRowCount(0)
            return

        items = [
            ("Lines", result.total, None),
            ("Changed", result.changed, theme.SUCCESS if result.changed else None),
            ("Removed", result.removals, theme.WARNING if result.removals else None),
        ]
        if result.dropped:
            items.append(("Dropped", result.dropped, theme.WARNING))
        self._stats.setText(stats_html(items))
        self._output.setPlainText("\n".join(result.lines))

        muted = QColor(theme.TEXT_MUTED)
        self._hits_table.setRowCount(len(result.phrase_hits))
        for row, (phrase, count) in enumerate(result.phrase_hits):
            # Show spaces at the edges so "Email: " and "Email:" can be told apart.
            shown = phrase.replace(" ", "·") if phrase != phrase.strip() else phrase
            phrase_item = QTableWidgetItem(shown)
            phrase_item.setToolTip(repr(phrase))
            count_item = QTableWidgetItem(format_number(count))
            count_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            if count == 0:
                phrase_item.setForeground(muted)
                count_item.setForeground(muted)
                phrase_item.setToolTip("This phrase was not found in the input.")
            self._hits_table.setItem(row, 0, phrase_item)
            self._hits_table.setItem(row, 1, count_item)
        self._result_tabs.setCurrentIndex(0)

    def _copy_output(self) -> None:
        if not self._result:
            return
        QGuiApplication.clipboard().setText("\n".join(self._result.lines))
        flash_button(self._copy_button, "Copied ✓")

    def _use_as_input(self) -> None:
        if self._result:
            self._input.setPlainText("\n".join(self._result.lines))
            self._input.setFocus()

    def load_demo(self) -> None:
        """Fill the page with sample data without touching the saved list (CI screenshots)."""
        self._persist_phrases = False
        self._presets = PresetLists({"Contact labels": "", "Price cleanup": "Price: \nTL"}, "Contact labels")
        self._preset_bar.set_presets(self._presets)
        self._phrases.setPlainText("Email: \nPhone: \nWebsite: https://\n(Sponsored)")
        self._input.setPlainText("\n".join([
            "Email: john@example.com",
            "Phone: +90 555 123 45 67",
            "Website: https://acme.example",
            "Email: jane@example.org (Sponsored)",
            "Address: Kadıköy, İstanbul",
        ]))
        self._on_done(run_job(self._input.toPlainText(), self._current_phrases(), self._options()))
