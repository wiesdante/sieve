"""Duplicate Remover: drop repeated lines from pasted text, entirely in the app."""

from __future__ import annotations

import logging

from PySide6.QtCore import Qt
from PySide6.QtGui import QGuiApplication, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
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
from sieve.ui.widgets import Page, StatTile, format_number, muted_label, primary_button

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


class DuplicateRemoverPage(Page):
    def __init__(self, context: AppContext) -> None:
        super().__init__(DuplicateRemoverTool.name, DuplicateRemoverTool.description)
        self._context = context
        self._prefs = context.tool_settings(TOOL_ID)
        self._task: BackgroundTask | None = None
        self._result: DedupeResult | None = None

        self.content.addWidget(self._build_input())
        self.content.addWidget(self._build_options())
        self.content.addLayout(self._build_run_row())
        self._results = self._build_results()
        self._results.hide()
        self.content.addWidget(self._results)
        self.finish()

        shortcut = QShortcut(QKeySequence("Ctrl+Return"), self)
        shortcut.activated.connect(self._run)

    # ----------------------------------------------------------------- input
    def _build_input(self) -> QGroupBox:
        group = QGroupBox("Girdi")
        layout = QVBoxLayout(group)

        self._input = QPlainTextEdit()
        self._input.setPlaceholderText("Satırları buraya yapıştır...")
        self._input.setMinimumHeight(200)
        self._input.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self._input.textChanged.connect(self._update_input_info)
        layout.addWidget(self._input)

        row = QHBoxLayout()
        paste = QPushButton("Panodan yapıştır")
        clear = QPushButton("Temizle")
        paste.clicked.connect(self._paste_from_clipboard)
        clear.clicked.connect(self._input.clear)
        row.addWidget(paste)
        row.addWidget(clear)
        row.addStretch(1)
        self._input_info = muted_label(wrap=False)
        row.addWidget(self._input_info)
        layout.addLayout(row)
        self._update_input_info()
        return group

    def _update_input_info(self) -> None:
        lines = self._input.blockCount() if self._input.toPlainText() else 0
        self._input_info.setText(f"{format_number(lines)} satır")

    def _paste_from_clipboard(self) -> None:
        text = QGuiApplication.clipboard().text()
        if text:
            self._input.setPlainText(text)

    # --------------------------------------------------------------- options
    def _build_options(self) -> QGroupBox:
        group = QGroupBox("Seçenekler")
        layout = QVBoxLayout(group)
        defaults = DedupeOptions()

        def checkbox(key: str, text: str, tooltip: str) -> QCheckBox:
            box = QCheckBox(text)
            box.setToolTip(tooltip)
            box.setChecked(bool(self._prefs.get(key, getattr(defaults, key))))
            box.toggled.connect(self._save_options)
            layout.addWidget(box)
            return box

        self._ignore_case = checkbox(
            "ignore_case",
            "Büyük/küçük harf farkını yok say (case-insensitive)",
            '"Apple" ve "apple" aynı satır sayılır. Türkçe İ/i doğru eşleşir.',
        )
        self._collapse_ws = checkbox(
            "collapse_whitespace",
            "Boşluk farklarını yok say (whitespace)",
            "Satır içindeki birden fazla boşluk ve tab, tek boşluk gibi karşılaştırılır.",
        )
        self._remove_empty = checkbox(
            "remove_empty",
            "Boş satırları sil",
            "Boş veya sadece boşluktan oluşan satırlar çıkarılır.",
        )
        self._output_normalized = checkbox(
            "output_normalized",
            "Çıktıyı normalize edilmiş haliyle yaz (küçük harf, tek boşluk)",
            "Kapalıyken her satırın ilk geçtiği orijinal hali yazılır. "
            "Açıkken eski script gibi küçük harfe çevrilmiş hali yazılır.",
        )

        sort_row = QHBoxLayout()
        sort_row.addWidget(QLabel("Sıralama:"))
        self._sort = QComboBox()
        for key, label in SORT_MODES.items():
            self._sort.addItem(label, key)
        index = self._sort.findData(self._prefs.get("sort", defaults.sort))
        self._sort.setCurrentIndex(max(index, 0))
        self._sort.currentIndexChanged.connect(self._save_options)
        sort_row.addWidget(self._sort)
        sort_row.addStretch(1)
        layout.addLayout(sort_row)
        return group

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

    # ------------------------------------------------------------------- run
    def _build_run_row(self) -> QHBoxLayout:
        row = QHBoxLayout()
        self._run_button = primary_button("Duplicate'leri temizle")
        self._run_button.setToolTip("Ctrl+Enter")
        self._run_button.clicked.connect(self._run)
        self._progress = QProgressBar()
        self._progress.setRange(0, 100)
        self._progress.hide()
        self._cancel_button = QPushButton("İptal")
        self._cancel_button.hide()
        self._cancel_button.clicked.connect(self._cancel)
        row.addWidget(self._run_button)
        row.addWidget(self._progress, 1)
        row.addWidget(self._cancel_button)
        row.addStretch(0)
        return row

    def _run(self) -> None:
        if self._task is not None:
            return
        text = self._input.toPlainText()
        if not text.strip():
            QMessageBox.information(self, "Duplicate Remover", "Önce temizlenecek metni yapıştır.")
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
        self._run_button.setEnabled(not running)
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

    # --------------------------------------------------------------- results
    def _build_results(self) -> QGroupBox:
        group = QGroupBox("Sonuç")
        layout = QVBoxLayout(group)

        tiles = QHBoxLayout()
        self._tile_total = StatTile("Toplam satır")
        self._tile_empty = StatTile("Boş satır")
        self._tile_removed = StatTile("Silinen duplicate")
        self._tile_unique = StatTile("Unique satır")
        for tile in (self._tile_total, self._tile_empty, self._tile_removed, self._tile_unique):
            tiles.addWidget(tile)
        layout.addLayout(tiles)

        self._result_tabs = QTabWidget()
        output_tab = QWidget()
        output_layout = QVBoxLayout(output_tab)
        output_layout.setContentsMargins(10, 10, 10, 10)
        self._output = QPlainTextEdit()
        self._output.setReadOnly(True)
        self._output.setMinimumHeight(240)
        self._output.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        output_layout.addWidget(self._output)
        output_buttons = QHBoxLayout()
        copy = primary_button("Sonucu kopyala")
        use_as_input = QPushButton("Sonucu girdiye taşı")
        use_as_input.setToolTip("Sonuç üzerinde farklı seçeneklerle tekrar çalışmak için.")
        copy.clicked.connect(self._copy_output)
        use_as_input.clicked.connect(self._use_as_input)
        output_buttons.addWidget(copy)
        output_buttons.addWidget(use_as_input)
        output_buttons.addStretch(1)
        self._output_note = muted_label(wrap=False)
        output_buttons.addWidget(self._output_note)
        output_layout.addLayout(output_buttons)
        self._result_tabs.addTab(output_tab, "Çıktı")

        dup_tab = QWidget()
        dup_layout = QVBoxLayout(dup_tab)
        dup_layout.setContentsMargins(10, 10, 10, 10)
        self._dup_table = QTableWidget(0, 2)
        self._dup_table.setHorizontalHeaderLabels(["Satır", "Tekrar"])
        self._dup_table.verticalHeader().hide()
        self._dup_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._dup_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        header = self._dup_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self._dup_table.setMinimumHeight(240)
        dup_layout.addWidget(self._dup_table)
        dup_buttons = QHBoxLayout()
        copy_dups = QPushButton("Duplicate listesini kopyala")
        copy_dups.clicked.connect(self._copy_duplicates)
        dup_buttons.addWidget(copy_dups)
        dup_buttons.addStretch(1)
        self._dup_note = muted_label(wrap=False)
        dup_buttons.addWidget(self._dup_note)
        dup_layout.addLayout(dup_buttons)
        self._result_tabs.addTab(dup_tab, "Duplicates")

        layout.addWidget(self._result_tabs)
        return group

    def _show_result(self, result: DedupeResult) -> None:
        self._tile_total.set_value(result.total)
        self._tile_empty.set_value(result.empty)
        self._tile_removed.set_value(result.removed, theme.WARNING if result.removed else None)
        self._tile_unique.set_value(result.unique, theme.SUCCESS)

        self._output.setPlainText("\n".join(result.lines))
        self._output_note.setText(f"{format_number(len(result.lines))} satır")

        rows = result.duplicates[:DUPLICATE_TABLE_LIMIT]
        self._dup_table.setRowCount(len(rows))
        for row, (line, count) in enumerate(rows):
            self._dup_table.setItem(row, 0, QTableWidgetItem(line))
            count_item = QTableWidgetItem(format_number(count))
            count_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self._dup_table.setItem(row, 1, count_item)
        total_dups = len(result.duplicates)
        self._result_tabs.setTabText(1, f"Duplicates ({format_number(total_dups)})")
        if total_dups > DUPLICATE_TABLE_LIMIT:
            self._dup_note.setText(
                f"En çok tekrar eden {format_number(DUPLICATE_TABLE_LIMIT)} satır gösteriliyor; "
                "kopyalama hepsini içerir."
            )
        else:
            self._dup_note.setText("")

        self._results.show()
        self.ensureWidgetVisible(self._results)

    def _copy_output(self) -> None:
        if self._result:
            QGuiApplication.clipboard().setText("\n".join(self._result.lines))
            self._output_note.setText("Sonuç panoya kopyalandı.")

    def _copy_duplicates(self) -> None:
        if not self._result or not self._result.duplicates:
            self._dup_note.setText("Tekrar eden satır yok.")
            return
        lines = [f"{line}\t{count}" for line, count in self._result.duplicates]
        QGuiApplication.clipboard().setText("\n".join(lines))
        self._dup_note.setText("Duplicate listesi panoya kopyalandı (satır ⇥ tekrar).")

    def _use_as_input(self) -> None:
        if self._result:
            self._input.setPlainText("\n".join(self._result.lines))
            self.ensureWidgetVisible(self._input)
