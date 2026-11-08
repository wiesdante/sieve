"""UI side of self-updating: checking, prompting, downloading, installing."""

from __future__ import annotations

import logging
from enum import Enum

from PySide6.QtCore import QObject, Qt, Signal
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QProgressDialog,
    QPushButton,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from sieve import __version__, paths, updater
from sieve.context import AppContext
from sieve.credentials import GITHUB_TOKEN
from sieve.ui.tasks import BackgroundTask, run_in_background
from sieve.ui.widgets import muted_label, primary_button

log = logging.getLogger(__name__)


class Choice(Enum):
    INSTALL = "install"
    LATER = "later"
    SKIP = "skip"


class UpdateDialog(QDialog):
    def __init__(self, release: updater.ReleaseInfo, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.choice = Choice.LATER
        self.setWindowTitle("Update available")
        self.setMinimumSize(520, 420)

        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        title = QLabel(f"Sieve {release.version} is available")
        title.setObjectName("PageTitle")
        layout.addWidget(title)
        layout.addWidget(muted_label(f"You have version {__version__}"))

        notes = QTextBrowser()
        notes.setOpenExternalLinks(True)
        notes.setMarkdown(release.notes or "_No release notes._")
        layout.addWidget(notes, 1)

        buttons = QHBoxLayout()
        skip = QPushButton("Skip this version")
        later = QPushButton("Later")
        install = primary_button("Update now")
        skip.clicked.connect(lambda: self._finish(Choice.SKIP))
        later.clicked.connect(lambda: self._finish(Choice.LATER))
        install.clicked.connect(lambda: self._finish(Choice.INSTALL))
        buttons.addWidget(skip)
        buttons.addStretch(1)
        buttons.addWidget(later)
        buttons.addWidget(install)
        layout.addLayout(buttons)
        install.setDefault(True)

    def _finish(self, choice: Choice) -> None:
        self.choice = choice
        self.accept()


class UpdateController(QObject):
    """Owns the update workflow; pages listen to ``status_changed``."""

    status_changed = Signal(str)

    def __init__(self, context: AppContext, window: QWidget) -> None:
        super().__init__(window)
        # Updates come from the public repository now; a token saved by an older
        # version is no longer needed, so it is not kept on the computer.
        try:
            if context.credentials.get(GITHUB_TOKEN):
                context.credentials.delete(GITHUB_TOKEN)
        except Exception:
            log.exception("Could not remove the old GitHub token")
        self._context = context
        self._window = window
        self._busy = False
        self._download: BackgroundTask | None = None
        self.status = ""

    def _set_status(self, text: str) -> None:
        self.status = text
        self.status_changed.emit(text)

    def check(self, manual: bool = False) -> None:
        if self._busy:
            return
        token = ""  # the repository is public

        self._busy = True
        self._set_status("Checking for updates...")
        run_in_background(
            updater.fetch_latest_release,
            token,
            on_success=lambda release: self._on_checked(release, manual),
            on_error=lambda exc: self._on_check_failed(exc, manual),
        )

    def _on_check_failed(self, exc: Exception, manual: bool) -> None:
        self._busy = False
        message = str(exc) if isinstance(exc, updater.UpdateError) else "An unexpected error occurred."
        log.warning("Update check failed: %s", exc)
        self._set_status(f"Update check failed: {message}")
        if manual:
            QMessageBox.warning(self._window, "Update check", message)

    def _on_checked(self, release: updater.ReleaseInfo | None, manual: bool) -> None:
        self._busy = False
        if release is None:
            self._set_status("No release has been published yet.")
            if manual:
                QMessageBox.information(self._window, "Update", "No published release was found.")
            return

        if not updater.is_newer(release.version):
            self._set_status(f"Sieve is up to date (v{__version__}).")
            if manual:
                QMessageBox.information(
                    self._window, "Update", f"You are using the latest version (v{__version__})."
                )
            return

        self._set_status(f"New version available: v{release.version}")
        settings = self._context.settings
        if not manual and settings.skipped_version == release.version:
            return

        dialog = UpdateDialog(release, self._window)
        dialog.exec()
        if dialog.choice is Choice.SKIP:
            settings.skipped_version = release.version
            self._context.save_settings()
        elif dialog.choice is Choice.INSTALL:
            self._start_download(release)

    def _start_download(self, release: updater.ReleaseInfo) -> None:
        token = ""
        progress = QProgressDialog(
            f"Downloading Sieve {release.version}...", "Cancel", 0, 100, self._window
        )
        progress.setWindowTitle("Update")
        progress.setWindowModality(Qt.WindowModality.WindowModal)
        progress.setMinimumDuration(0)
        progress.setAutoClose(False)
        progress.setAutoReset(False)
        progress.setValue(0)

        def on_progress(done: int, total: int) -> None:
            if total:
                progress.setValue(int(done * 100 / total))
                progress.setLabelText(
                    f"Downloading Sieve {release.version}... "
                    f"{done / 1_048_576:.1f} / {total / 1_048_576:.1f} MB"
                )

        def on_success(installer) -> None:
            progress.close()
            self._busy = False
            self._install(installer)

        def on_error(exc: Exception) -> None:
            progress.close()
            self._busy = False
            if isinstance(exc, updater.UpdateCancelledError):
                self._set_status("Update cancelled.")
                return
            message = str(exc) if isinstance(exc, updater.UpdateError) else "The download failed."
            log.warning("Update download failed: %s", exc)
            self._set_status(f"Download failed: {message}")
            QMessageBox.warning(self._window, "Update", message)

        self._busy = True
        self._download = run_in_background(
            updater.download_installer,
            release,
            token,
            on_success=on_success,
            on_error=on_error,
            on_progress=on_progress,
        )
        progress.canceled.connect(self._download.cancel)
        progress.show()

    def _install(self, installer) -> None:
        if not paths.is_frozen():
            QMessageBox.information(
                self._window,
                "Development mode",
                f"The installer was downloaded to:\n{installer}\n\n"
                "It is not started automatically when running from source.",
            )
            return
        try:
            updater.launch_installer(installer)
        except Exception as exc:
            log.exception("Could not start installer")
            QMessageBox.critical(self._window, "Update", f"Could not start the installer: {exc}")
            return
        QApplication.quit()
