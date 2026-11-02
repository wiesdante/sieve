"""Duplicate Remover: drop repeated lines from pasted text, entirely in the app.

The page fits in one screen: options on top, input on the left, output on the
right, so paste → clean → copy never needs scrolling.
"""

from __future__ import annotations

import logging

from PySide6.QtCore import QByteArray, Qt
from PySide6.QtGui import QGuiApplication, QKeySequence, QShortcut
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
    QVBoxLayout,
    QWidget,
)

from sieve.context import AppContext
from sieve.core.dedupe import (
    SORT_MODES,
    DedupeCancelledError,
    DedupeOptions,
    DedupeResult,
    remove_duplicates,
)
from sieve.tools.base import Tool
from sieve.ui import theme
from sieve.ui.tasks import BackgroundTask, run_in_background
from sieve.ui.widgets import ToolPage, flash_button, format_number, muted_label, primary_button

log = logging.getLogger(__name__)

TOOL_ID = "duplicate_remover"
DUPLICATE_TABLE_LIMIT = 1_000


class DuplicateRemoverTool(Tool):
    id = TOOL_ID
    name = "Duplicate Remover"
    description = "Tekrar eden satırları temizler; her satırın ilk geçtiği hali ve sırayı korur."
    category = "Metin İşlemleri"

    def create_widget(self, context: AppContext) -> QWidget:
        return DuplicateRemoverPage(context)


def run_job(text: str, options: DedupeOptions, progress=None, cancelled=None) -> DedupeResult:
    return remove_duplicates(text.splitlines(), options, progress=progress, cancelled=cancelled)


def _flat_button(text: str, tooltip: str = "") -> QPushButton:
    button = QPushButton(text)
    button.setProperty("flat", True)
    button.setCursor(Qt.CursorShape.PointingHandCursor)
    if tooltip:
        button.setToolTip(tooltip)
    return button


def _panel(title: str) -> tuple[QFrame, QVBoxLayout, QHBoxLayout]:
    """A rounded panel with a header row; returns (panel, body layout, header layout)."""
    panel = QFrame()
    panel.setObjectName("Panel")
    body = QVBoxLayout(panel)
    body.setContentsMargins(14, 12, 14, 12)
    body.setSpacing(8)
    header = QHBoxLayout()
    header.setSpacing(6)
    label = QLabel(title)
    label.setObjectName("PanelTitle")
    header.addWidget(label)
    body.addLayout(header)
    return panel, body, header


class DuplicateRemoverPage(ToolPage):
    def __init__(self, context: AppContext) -> None:
        super().__init__(DuplicateRemoverTool.name, DuplicateRemoverTool.description)
        self._context = context
        self._prefs = context.tool_settings(TOOL_ID)
        self._task: BackgroundTask | None = None
        self._result: DedupeResult | None = None

        self.content.addWidget(self._build_toolbar())

        self._splitter = QSplitter(Qt.Orientation.Horizontal)
        self._splitter.setChildrenCollapsible(False)
        self._splitter.setHandleWidth(12)
        self._splitter.addWidget(self._build_input_panel())
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

        self._show_result(None)

    # --------------------------------------------------------------- toolbar
    def _build_toolbar(self) -> QFrame:
        bar = QFrame()
        bar.setObjectName("Toolbar")
        row = QHBoxLayout(bar)
        row.setContentsMargins(14, 8, 14, 8)
        row.setSpacing(18)
        defaults = DedupeOptions()

        def checkbox(key: str, text: str, tooltip: str) -> QCheckBox:
            box = QCheckBox(text)
            box.setToolTip(tooltip)
            box.setChecked(bool(self._prefs.get(key, getattr(defaults, key))))
            box.toggled.connect(self._save_options)
            row.addWidget(box)
            return box

        self._ignore_case = checkbox(
            "ignore_case",
            "Case-insensitive",
            'Büyük/küçük harf farkı yok sayılır: "Apple" ve "apple" aynı satırdır. '
            "Türkçe İ/i doğru eşleşir.",
        )
        self._collapse_ws = checkbox(
            "collapse_whitespace",
            "Whitespace'i yok say",
            "Satır içindeki birden fazla boşluk ve tab, tek boşluk gibi karşılaştırılır.",
        )
        self._remove_empty = checkbox(
            "remove_empty", "Boş satırları sil", "Boş veya sadece boşluktan oluşan satırlar çıkarılır."
        )
        self._output_normalized = checkbox(
            "output_normalized",
            "Normalize çıktı",
            "Kapalıyken her satırın ilk geçtiği orijinal hali yazılır.\n"
            "Açıkken eski script gibi küçük harfe çevrilmiş, tek boşluklu hali yazılır.",
        )
        row.addStretch(1)
        row.addWidget(muted_label("Sıralama", wrap=False))
        self._sort = QComboBox()
        for key, label in SORT_MODES.items():
            self._sort.addItem(label, key)
        index = self._sort.findData(self._prefs.get("sort", defaults.sort))
        self._sort.setCurrentIndex(max(index, 0))
        self._sort.currentIndexChanged.connect(self._save_options)
        row.addWidget(self._sort)
        return bar

    def _options(self) -> DedupeOptions:
        return DedupeOptions(
            ignore_case=self._ignore_case.isChecked(),
            collapse_whitespace=self._collapse_ws.isChecked(),
            remove_empty=self._remove_empty.isChecked(),
            output_normalized=self._output_normalized.isChecked(),
            sort=self._sort.currentData(),
        )

    def _save_options(self) -> None:
        options = self._options()
        self._prefs.update(
            ignore_case=options.ignore_case,
            collapse_whitespace=options.collapse_whitespace,
            remove_empty=options.remove_empty,
            output_normalized=options.output_normalized,
            sort=options.sort,
        )
        self._context.save_settings()

    def _save_splitter(self) -> None:
        self._prefs["splitter"] = bytes(self._splitter.saveState().toBase64()).decode("ascii")
        self._context.save_settings()

    # ----------------------------------------------------------------- input
    def _build_input_panel(self) -> QFrame:
        panel, body, header = _panel("Girdi")
        self._input_info = muted_label(wrap=False)
        header.addWidget(self._input_info)
        header.addStretch(1)
        paste = _flat_button("Yapıştır", "Panodaki metni girdiye yapıştırır.")
        clear = _flat_button("Boşalt", "Girdiyi temizler.")
        paste.clicked.connect(self._paste_from_clipboard)
        clear.clicked.connect(self._clear_input)
        header.addWidget(paste)
        header.addWidget(clear)

        self._input = QPlainTextEdit()
        self._input.setObjectName("Editor")
        self._input.setPlaceholderText("Satırları buraya yapıştır...")
        self._input.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self._input.textChanged.connect(self._update_input_info)
        body.addWidget(self._input, 1)

        footer = QHBoxLayout()
        footer.setSpacing(8)
        self._run_button = primary_button("Duplicate'leri temizle")
        self._run_button.setToolTip("Ctrl+Enter")
        self._run_button.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._run_button.clicked.connect(self._run)
        self._paste_run_button = QPushButton("Yapıştır ve temizle")
        self._paste_run_button.setToolTip(
            "Panodaki metni yapıştırır ve hemen temizler. Tek tıkla sonuç."
        )
        self._paste_run_button.clicked.connect(self._paste_and_run)
        self._progress = QProgressBar()
        self._progress.setRange(0, 100)
        self._progress.hide()
        self._cancel_button = QPushButton("İptal")
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
        self._input_info.setText(f"· {format_number(lines)} satır")

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
            flash_button(self._paste_run_button, "Pano boş")

    # ---------------------------------------------------------------- output
    def _build_output_panel(self) -> QFrame:
        panel, body, header = _panel("Çıktı")
        self._stats = QLabel()
        self._stats.setObjectName("Stats")
        self._stats.setTextFormat(Qt.TextFormat.RichText)
        header.addWidget(self._stats)
        header.addStretch(1)
        self._copy_button = primary_button("Kopyala")
        self._copy_button.setToolTip("Sonucun tamamını panoya kopyalar (Ctrl+Shift+C).")
        self._copy_button.clicked.connect(self._copy_output)
        header.addWidget(self._copy_button)

        self._result_tabs = QTabWidget()
        self._output = QPlainTextEdit()
        self._output.setObjectName("Editor")
        self._output.setReadOnly(True)
        self._output.setPlaceholderText("Sonuç burada görünecek.")
        self._output.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self._result_tabs.addTab(self._output, "Sonuç")

        self._dup_table = QTableWidget(0, 2)
        self._dup_table.setHorizontalHeaderLabels(["Satır", "Tekrar"])
        self._dup_table.verticalHeader().hide()
        self._dup_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._dup_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        table_header = self._dup_table.horizontalHeader()
        table_header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        table_header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self._result_tabs.addTab(self._dup_table, "Duplicates")
        body.addWidget(self._result_tabs, 1)

        footer = QHBoxLayout()
        footer.setSpacing(6)
        self._to_input_button = _flat_button(
            "Girdiye taşı", "Sonuç üzerinde farklı seçeneklerle tekrar çalışmak için."
        )
        self._copy_dups_button = _flat_button(
            "Duplicate listesini kopyala", "Tekrar eden satırları ve tekrar sayılarını kopyalar."
        )
        self._to_input_button.clicked.connect(self._use_as_input)
        self._copy_dups_button.clicked.connect(self._copy_duplicates)
        footer.addWidget(self._to_input_button)
        footer.addWidget(self._copy_dups_button)
        footer.addStretch(1)
        self._auto_copy = QCheckBox("Sonucu otomatik kopyala")
        self._auto_copy.setToolTip("Temizleme bitince sonuç kendiliğinden panoya kopyalanır.")
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
            flash_button(self._run_button, "Önce metin yapıştır")
            return
        self._set_running(True)
        self._task = run_in_background(
            run_job,
            text,
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
        if isinstance(exc, DedupeCancelledError):
            return
        log.error("Duplicate removal failed", exc_info=exc)
        QMessageBox.critical(self, "Duplicate Remover", f"Beklenmeyen bir hata oluştu:\n{exc}")

    def _on_done(self, result: DedupeResult) -> None:
        self._task = None
        self._set_running(False)
        self._result = result
        self._show_result(result)
        if self._auto_copy.isChecked():
            self._copy_output()

    def _show_result(self, result: DedupeResult | None) -> None:
        has_result = result is not None
        for button in (self._copy_button, self._to_input_button, self._copy_dups_button):
            button.setEnabled(has_result)
        if result is None:
            self._stats.setText("")
            self._output.clear()
            self._dup_table.setRowCount(0)
            return

        def stat(label: str, value: int, color: str | None = None) -> str:
            number = format_number(value)
            if color:
                number = f'<span style="color:{color}; font-weight:600">{number}</span>'
            else:
                number = f'<span style="color:{theme.TEXT}; font-weight:600">{number}</span>'
            return f"{label} {number}"

        self._stats.setText(
            "&nbsp;&nbsp;·&nbsp;&nbsp;".join([
                stat("Toplam", result.total),
                stat("Boş", result.empty),
                stat("Silinen", result.removed, theme.WARNING if result.removed else None),
                stat("Unique", result.unique, theme.SUCCESS),
            ])
        )

        self._output.setPlainText("\n".join(result.lines))

        rows = result.duplicates[:DUPLICATE_TABLE_LIMIT]
        self._dup_table.setRowCount(len(rows))
        for row, (line, count) in enumerate(rows):
            self._dup_table.setItem(row, 0, QTableWidgetItem(line))
            count_item = QTableWidgetItem(format_number(count))
            count_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self._dup_table.setItem(row, 1, count_item)
        self._result_tabs.setTabText(1, f"Duplicates ({format_number(len(result.duplicates))})")
        self._result_tabs.setCurrentIndex(0)

    def _copy_output(self) -> None:
        if not self._result:
            return
        QGuiApplication.clipboard().setText("\n".join(self._result.lines))
        flash_button(self._copy_button, "Kopyalandı ✓")

    def _copy_duplicates(self) -> None:
        if not self._result:
            return
        if not self._result.duplicates:
            flash_button(self._copy_dups_button, "Tekrar eden satır yok")
            return
        lines = [f"{line}\t{count}" for line, count in self._result.duplicates]
        QGuiApplication.clipboard().setText("\n".join(lines))
        flash_button(self._copy_dups_button, "Kopyalandı ✓")

    def load_demo(self) -> None:
        """Fill the page with sample data (used for CI screenshots)."""
        sample = "\n".join(
            ["https://example.com/a", "https://example.com/A ", "https://example.com/b", "",
             "Ürün listesi", "ürün   listesi", "İstanbul", "istanbul", "https://example.com/c"] * 3
        )
        self._input.setPlainText(sample)
        self._on_done(run_job(sample, self._options()))

    def _use_as_input(self) -> None:
        if self._result:
            self._input.setPlainText("\n".join(self._result.lines))
            self._input.setFocus()
