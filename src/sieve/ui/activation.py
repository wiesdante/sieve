"""Activation: the window that asks for a code, and the owner's code generator.

``ActivationDialog`` appears at start-up until this computer has a valid code.
``OwnerDialog`` is where the owner sets up the passphrase once and later issues
codes; without the passphrase it can do nothing.
"""

from __future__ import annotations

import logging

from PySide6.QtCore import Qt
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from sieve import licensing_key
from sieve.core.licensing import (
    DURATIONS,
    MIN_PASSPHRASE,
    License,
    LicenseError,
    issue_code,
    machine_code,
    owner_key,
    public_key_text,
    read_code,
    signing_key,
)
from sieve.settings import Settings
from sieve.ui import theme
from sieve.ui.widgets import (
    compact_button,
    flash_button,
    muted_label,
    primary_button,
    prompt_header,
)

log = logging.getLogger(__name__)


def activation_required() -> bool:
    return bool(licensing_key.PUBLIC_KEY)


def current_license(settings: Settings) -> License | None:
    """This computer's valid license, or None."""
    if not settings.activation_code or not licensing_key.PUBLIC_KEY:
        return None
    try:
        return read_code(settings.activation_code, licensing_key.PUBLIC_KEY)
    except LicenseError:
        return None


def license_summary(settings: Settings) -> str:
    if not activation_required():
        return "Activation is not switched on."
    found = current_license(settings)
    if found is None:
        return "Not activated."
    if found.expires is None:
        return "Activated · no end date."
    left = found.days_left()
    return f"Activated · until {found.expires:%d %b %Y} ({left} days left)."


def _busy(work):
    """Run ``work`` with a wait cursor (the passphrase check takes a moment)."""
    QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
    try:
        return work()
    finally:
        QApplication.restoreOverrideCursor()


def _passphrase_field(placeholder: str = "Owner passphrase") -> QLineEdit:
    field = QLineEdit()
    field.setEchoMode(QLineEdit.EchoMode.Password)
    field.setPlaceholderText(placeholder)
    return field


def _copy_row(text: str, tooltip: str) -> tuple[QHBoxLayout, QLineEdit]:
    row = QHBoxLayout()
    value = QLineEdit(text)
    value.setReadOnly(True)
    copy = compact_button("Copy", tooltip)
    copy.clicked.connect(lambda: (QGuiApplication.clipboard().setText(value.text()), flash_button(copy, "Copied")))
    row.addWidget(value, 1)
    row.addWidget(copy)
    return row, value


def _message(text: str = "") -> QLabel:
    label = QLabel(text)
    label.setWordWrap(True)
    label.setStyleSheet(f"color: {theme.DANGER};")
    return label


class ActivationDialog(QDialog):
    """Asks for this computer's activation code; accepted once a valid code is saved."""

    def __init__(self, settings: Settings, save_settings, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._settings = settings
        self._save_settings = save_settings
        self.setWindowTitle("Activate Sieve")
        self.setMinimumWidth(620)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(10)
        layout.addWidget(prompt_header("Activate", "Sieve needs an activation code for this computer."))
        layout.addSpacing(6)
        layout.addWidget(muted_label(
            "Send this computer's code to wiesdante to ask for access. "
            "The activation code you get back works on this computer only."
        ))
        row, self._machine = _copy_row(machine_code(), "Copy this computer's code.")
        self._machine.setStyleSheet(f"color: {theme.ACCENT}; font-weight: 700;")
        layout.addLayout(row)

        layout.addSpacing(6)
        layout.addWidget(muted_label("Activation code", wrap=False))
        self._code = QPlainTextEdit()
        self._code.setObjectName("Editor")
        self._code.setPlaceholderText("Paste the activation code here")
        self._code.setFixedHeight(84)
        if settings.activation_code:
            self._code.setPlainText(settings.activation_code)
        layout.addWidget(self._code)
        self._error = _message()
        layout.addWidget(self._error)

        buttons = QHBoxLayout()
        owner = QPushButton("I'm the owner")
        owner.setToolTip("Activate this computer with the owner passphrase.")
        owner.clicked.connect(self._owner)
        quit_button = QPushButton("Quit")
        quit_button.clicked.connect(self.reject)
        activate = primary_button("Activate")
        activate.clicked.connect(self._activate)
        buttons.addWidget(owner)
        buttons.addStretch(1)
        buttons.addWidget(quit_button)
        buttons.addWidget(activate)
        layout.addLayout(buttons)
        if settings.activation_code:
            self._activate()  # explain why the saved code no longer works
            if self.result() == QDialog.DialogCode.Accepted:
                return

    def _save(self, code: str) -> None:
        self._settings.activation_code = code
        try:
            self._save_settings()
        except OSError:
            log.exception("Could not save the activation code")

    def _activate(self) -> None:
        code = self._code.toPlainText().strip()
        try:
            read_code(code, licensing_key.PUBLIC_KEY)
        except LicenseError as exc:
            self._error.setText(str(exc))
            return
        self._save(code)
        self.accept()

    def _owner(self) -> None:
        dialog = QDialog(self)
        dialog.setWindowTitle("Owner")
        form = QVBoxLayout(dialog)
        form.setContentsMargins(20, 18, 20, 18)
        form.addWidget(muted_label("Enter the owner passphrase to activate this computer with no end date."))
        field = _passphrase_field()
        form.addWidget(field)
        error = _message()
        form.addWidget(error)
        row = QHBoxLayout()
        row.addStretch(1)
        go = primary_button("Activate")
        row.addWidget(go)
        form.addLayout(row)

        def submit() -> None:
            try:
                key = _busy(lambda: owner_key(field.text(), licensing_key.PUBLIC_KEY))
            except LicenseError as exc:
                error.setText(str(exc))
                return
            code = issue_code(key, machine_code(), None)
            field.clear()
            self._save(code)
            dialog.accept()
            self.accept()

        go.clicked.connect(submit)
        field.returnPressed.connect(submit)
        dialog.exec()


class OwnerDialog(QDialog):
    """Set up the owner passphrase (once), then issue activation codes with it."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Activation codes")
        self.setMinimumWidth(640)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(10)
        if licensing_key.PUBLIC_KEY:
            self._build_issue(layout)
        else:
            self._build_setup(layout)

    # ----------------------------------------------------------- set up
    def _build_setup(self, layout: QVBoxLayout) -> None:
        layout.addWidget(prompt_header("Owner setup", "Choose the passphrase that will issue activation codes."))
        layout.addWidget(muted_label(
            f"Use at least {MIN_PASSPHRASE} characters, for example four or five unrelated words. "
            "The passphrase is never saved: you type it each time you issue a code. If you forget it, "
            "no new codes can be made (codes already given keep working). Do not share it with anyone."
        ))
        form = QFormLayout()
        self._first = _passphrase_field("Passphrase")
        self._second = _passphrase_field("The same passphrase again")
        form.addRow("Passphrase", self._first)
        form.addRow("Again", self._second)
        layout.addLayout(form)
        self._error = _message()
        layout.addWidget(self._error)
        make = primary_button("Create public key")
        make.clicked.connect(self._create_public_key)
        row = QHBoxLayout()
        row.addStretch(1)
        row.addWidget(make)
        layout.addLayout(row)
        layout.addWidget(muted_label(
            "Then send the public key below to your developer. It is not secret and cannot be used to "
            "make codes; it lets the app check them."
        ))
        key_row, self._public = _copy_row("", "Copy the public key.")
        self._public.setPlaceholderText("The public key appears here")
        layout.addLayout(key_row)

    def _create_public_key(self) -> None:
        first, second = self._first.text(), self._second.text()
        if first != second:
            self._error.setText("The two passphrases are different.")
            return
        try:
            key = _busy(lambda: signing_key(first))
        except LicenseError as exc:
            self._error.setText(str(exc))
            return
        self._error.setText("")
        self._first.clear()
        self._second.clear()
        self._public.setText(public_key_text(key))

    # ------------------------------------------------------------- issue
    def _build_issue(self, layout: QVBoxLayout) -> None:
        layout.addWidget(prompt_header("Activation codes", "Issue a code for someone's computer."))
        form = QFormLayout()
        form.setHorizontalSpacing(14)
        self._machine = QLineEdit()
        self._machine.setPlaceholderText("Their computer's code, e.g. 7K3F-9QX2-MW4D-QZ8A")
        self._duration = QComboBox()
        for label, days in DURATIONS:
            self._duration.addItem(label, days)
        self._passphrase = _passphrase_field()
        form.addRow("Computer", self._machine)
        form.addRow("Valid for", self._duration)
        form.addRow("Passphrase", self._passphrase)
        layout.addLayout(form)
        self._error = _message()
        layout.addWidget(self._error)
        row = QHBoxLayout()
        this_pc = QPushButton("Use this computer")
        this_pc.clicked.connect(lambda: self._machine.setText(machine_code()))
        row.addWidget(this_pc)
        row.addStretch(1)
        make = primary_button("Generate code")
        make.clicked.connect(self._issue)
        row.addWidget(make)
        layout.addLayout(row)
        self._passphrase.returnPressed.connect(self._issue)
        layout.addWidget(muted_label("Activation code (send this back):", wrap=False))
        self._output = QPlainTextEdit()
        self._output.setObjectName("Editor")
        self._output.setReadOnly(True)
        self._output.setFixedHeight(84)
        layout.addWidget(self._output)
        copy = compact_button("Copy code")
        copy.clicked.connect(lambda: (QGuiApplication.clipboard().setText(self._output.toPlainText()),
                                      flash_button(copy, "Copied")))
        copy_row = QHBoxLayout()
        copy_row.addStretch(1)
        copy_row.addWidget(copy)
        layout.addLayout(copy_row)

    def _issue(self) -> None:
        try:
            key = _busy(lambda: owner_key(self._passphrase.text(), licensing_key.PUBLIC_KEY))
            code = issue_code(key, self._machine.text(), self._duration.currentData())
        except LicenseError as exc:
            self._error.setText(str(exc))
            return
        self._error.setText("")
        self._output.setPlainText(code)
