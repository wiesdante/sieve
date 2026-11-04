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
            box = QMessageBox(QMessageBox.Icon.Critical, APP_NAME, "An unexpected error occurred.")
            box.setInformativeText(
                f"Details were written to the log file:\n{paths.logs_dir() / 'sieve.log'}"
            )
            box.setDetailedText(details)
            box.exec()

    sys.excepthook = hook


def _run_smoke_test(app, window, screenshot_dir: str | None) -> int:
    """Open every page and exit; used by CI. Optionally saves a screenshot of each page."""
    from pathlib import Path

    if screenshot_dir:
        Path(screenshot_dir).mkdir(parents=True, exist_ok=True)
        window.resize(1280, 800)
        window.show()
    for key in window.page_keys():
        window.navigate(key)
        app.processEvents()
        if window.current_page_key() != key:
            log.error("Smoke test could not open page %s", key)
            return 1
        if screenshot_dir:
            name = key.replace(":", "_")
            window.grab().save(str(Path(screenshot_dir) / f"{name}.png"))
            page = window.current_page()
            if hasattr(page, "load_demo"):
                page.load_demo()
                app.processEvents()
                window.grab().save(str(Path(screenshot_dir) / f"{name}_demo.png"))
    from sieve.tools import all_tools

    for tool in all_tools():
        try:
            tool.self_check()
        except Exception:
            log.exception("Self-check failed for tool %s", tool.id)
            return 1
    log.info("Smoke test passed")
    return 0


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv if argv is None else argv)
    smoke_test = "--smoke-test" in argv
    screenshot_dir = next(
        (arg.split("=", 1)[1] for arg in argv if arg.startswith("--screenshots=")), None
    )

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
        return _run_smoke_test(app, window, screenshot_dir)

    updater.clean_old_downloads()
    window.show()
    window.start_background_checks()
    return app.exec()
