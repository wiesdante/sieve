"""Application bootstrap."""

from __future__ import annotations

import contextlib
import logging
import sys
import traceback

from sieve import APP_NAME, AUTHOR, __version__, paths, updater
from sieve.logging_setup import configure_logging

log = logging.getLogger(__name__)

APP_USER_MODEL_ID = f"{AUTHOR}.{APP_NAME}"


def _set_windows_app_id() -> None:
    """Give the process its own taskbar identity so our icon is used."""
    if sys.platform == "win32":
        import ctypes

        with contextlib.suppress(AttributeError, OSError):
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(APP_USER_MODEL_ID)


def _install_exception_hook() -> None:
    from PySide6.QtWidgets import QApplication, QMessageBox

    def hook(exc_type, exc, tb) -> None:
        log.critical("Unhandled exception", exc_info=(exc_type, exc, tb))
        if QApplication.instance() is not None:
            details = "".join(traceback.format_exception(exc_type, exc, tb))
            box = QMessageBox(QMessageBox.Icon.Critical, APP_NAME, "Beklenmeyen bir hata oluştu.")
            box.setInformativeText(
                f"Ayrıntılar log dosyasına yazıldı:\n{paths.logs_dir() / 'sieve.log'}"
            )
            box.setDetailedText(details)
            box.exec()

    sys.excepthook = hook


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv if argv is None else argv)
    smoke_test = "--smoke-test" in argv

    configure_logging()
    log.info("Starting %s %s (frozen=%s)", APP_NAME, __version__, paths.is_frozen())
    _set_windows_app_id()

    from PySide6.QtWidgets import QApplication

    from sieve.context import AppContext
    from sieve.ui.main_window import MainWindow
    from sieve.ui.theme import apply_theme

    app = QApplication(argv)
    app.setApplicationName(APP_NAME)
    app.setApplicationVersion(__version__)
    app.setOrganizationName(AUTHOR)
    apply_theme(app)
    _install_exception_hook()

    window = MainWindow(AppContext())

    if smoke_test:
        # Used by the release pipeline: build every page, then exit cleanly.
        for key in window.page_keys():
            window.navigate(key)
            app.processEvents()
            if window.current_page_key() != key:
                log.error("Smoke test could not open page %s", key)
                return 1
        log.info("Smoke test passed")
        return 0

    updater.clean_old_downloads()
    window.show()
    window.start_background_checks()
    return app.exec()
