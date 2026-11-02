"""Settings page: GitHub token, update preferences, proxies, folders."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QTextBrowser,
    QVBoxLayout,
)

from sieve import GITHUB_REPO, paths, updater
from sieve.context import AppContext
from sieve.credentials import GITHUB_TOKEN
from sieve.proxy import ROTATION_MODES, ProxyCheckResult, check_proxy, parse_proxy_list
from sieve.ui import theme
from sieve.ui.tasks import run_in_background
from sieve.ui.widgets import Page, muted_label, open_folder, primary_button

TOKEN_HELP = f"""
### How to create a GitHub token

Sieve downloads updates from the private `{GITHUB_REPO}` repository. A token with
**read-only** access is all it needs.

1. On GitHub, open **Settings → Developer settings → Personal access tokens →
   Fine-grained tokens** and click **Generate new token**.
2. **Token name**: for example `Sieve updates`.
3. **Expiration**: any duration you like. When it expires, just paste a new one here.
4. **Repository access**: **Only select repositories** → `{GITHUB_REPO.split('/')[1]}`.
5. **Permissions → Repository permissions → Contents**: **Read-only**.
   (Metadata is added as read-only automatically.)
6. Click **Generate token**, copy the value and paste it here.

The token is stored on this computer encrypted with Windows DPAPI and can only be
decrypted by your Windows user.
"""


class SettingsPage(Page):
    token_changed = Signal()

    def __init__(self, context: AppContext) -> None:
        super().__init__("Settings")
        self._context = context
        self.content.addWidget(self._build_updates_group())
        self.content.addWidget(self._build_proxy_group())
        self.content.addWidget(self._build_folders_group())
        self.finish()
        self._load()

    # ---------------------------------------------------------------- updates
    def _build_updates_group(self) -> QGroupBox:
        group = QGroupBox("GitHub && Updates")
        layout = QVBoxLayout(group)

        self._token_input = QLineEdit()
        self._token_input.setEchoMode(QLineEdit.EchoMode.Password)
        self._token_input.setPlaceholderText("github_pat_...")
        show = QPushButton("Show")
        show.setCheckable(True)
        show.toggled.connect(
            lambda on: (
                self._token_input.setEchoMode(
                    QLineEdit.EchoMode.Normal if on else QLineEdit.EchoMode.Password
                ),
                show.setText("Hide" if on else "Show"),
            )
        )
        token_row = QHBoxLayout()
        token_row.addWidget(self._token_input, 1)
        token_row.addWidget(show)

        form = QFormLayout()
        form.addRow("GitHub token", token_row)
        layout.addLayout(form)

        self._token_status = muted_label()
        layout.addWidget(self._token_status)

        buttons = QHBoxLayout()
        save = primary_button("Save && test")
        remove = QPushButton("Remove token")
        help_button = QPushButton("How to create a token")
        save.clicked.connect(self._save_token)
        remove.clicked.connect(self._remove_token)
        help_button.clicked.connect(self._show_token_help)
        buttons.addWidget(save)
        buttons.addWidget(remove)
        buttons.addStretch(1)
        buttons.addWidget(help_button)
        layout.addLayout(buttons)

        self._auto_check = QCheckBox("Check for updates on startup")
        self._auto_check.toggled.connect(self._save_update_prefs)
        layout.addWidget(self._auto_check)
        return group

    def _set_token_status(self, text: str, color: str = theme.TEXT_MUTED) -> None:
        self._token_status.setText(text)
        self._token_status.setStyleSheet(f"color: {color};")

    def _save_token(self) -> None:
        token = self._token_input.text().strip()
        if not token:
            QMessageBox.information(self, "Token", "Paste a token first.")
            return
        self._set_token_status("Testing token...")

        def on_success(repo: str) -> None:
            self._context.credentials.set(GITHUB_TOKEN, token)
            self._token_input.clear()
            self._set_token_status(f"Token saved. It has access to {repo}.", theme.SUCCESS)
            self.token_changed.emit()

        def on_error(exc: Exception) -> None:
            message = str(exc) if isinstance(exc, updater.UpdateError) else "Unexpected error."
            self._set_token_status(f"Token not saved: {message}", theme.DANGER)

        run_in_background(updater.verify_token, token, on_success=on_success, on_error=on_error)

    def _remove_token(self) -> None:
        if not self._context.credentials.get(GITHUB_TOKEN):
            return
        answer = QMessageBox.question(
            self, "Remove token", "Remove the saved GitHub token?"
        )
        if answer == QMessageBox.StandardButton.Yes:
            self._context.credentials.delete(GITHUB_TOKEN)
            self._set_token_status("No token saved.")
            self.token_changed.emit()

    def _show_token_help(self) -> None:
        dialog = QDialog(self)
        dialog.setWindowTitle("GitHub token")
        dialog.resize(560, 460)
        layout = QVBoxLayout(dialog)
        browser = QTextBrowser()
        browser.setMarkdown(TOKEN_HELP)
        layout.addWidget(browser)
        close = QPushButton("Close")
        close.clicked.connect(dialog.accept)
        layout.addWidget(close)
        dialog.exec()

    def _save_update_prefs(self) -> None:
        self._context.settings.check_updates_on_startup = self._auto_check.isChecked()
        self._context.save_settings()

    # ------------------------------------------------------------------ proxy
    def _build_proxy_group(self) -> QGroupBox:
        group = QGroupBox("Proxy")
        layout = QVBoxLayout(group)
        layout.addWidget(muted_label(
            "This proxy list is shared by every tool that supports proxies. "
            "One proxy per line: host:port, host:port:user:pass, user:pass@host:port "
            "or a full address starting with http:// or socks5://."
        ))

        self._proxy_enabled = QCheckBox("Use proxies")
        self._rotation = QComboBox()
        for key, label in ROTATION_MODES.items():
            self._rotation.addItem(label, key)
        top = QHBoxLayout()
        top.addWidget(self._proxy_enabled)
        top.addStretch(1)
        top.addWidget(muted_label("Rotation:", wrap=False))
        top.addWidget(self._rotation)
        layout.addLayout(top)

        self._proxy_list = QPlainTextEdit()
        self._proxy_list.setPlaceholderText("127.0.0.1:8080\nuser:pass@proxy.example.com:3128")
        self._proxy_list.setMinimumHeight(140)
        layout.addWidget(self._proxy_list)

        self._proxy_summary = muted_label()
        layout.addWidget(self._proxy_summary)

        buttons = QHBoxLayout()
        save = primary_button("Save")
        self._test_button = QPushButton("Test proxies")
        save.clicked.connect(self._save_proxies)
        self._test_button.clicked.connect(self._test_proxies)
        buttons.addWidget(save)
        buttons.addWidget(self._test_button)
        buttons.addStretch(1)
        layout.addLayout(buttons)

        self._proxy_results = QPlainTextEdit()
        self._proxy_results.setReadOnly(True)
        self._proxy_results.setMinimumHeight(110)
        self._proxy_results.hide()
        layout.addWidget(self._proxy_results)
        return group

    def _save_proxies(self) -> None:
        lines = self._proxy_list.toPlainText().splitlines()
        proxies, errors = parse_proxy_list(lines)
        settings = self._context.settings
        settings.proxy_enabled = self._proxy_enabled.isChecked()
        settings.proxy_rotation = self._rotation.currentData()
        settings.proxies = [line.strip() for line in lines if line.strip()]
        self._context.save_settings()

        summary = f"{len(proxies)} proxies saved."
        if errors:
            summary += f" {len(errors)} lines could not be read: " + "; ".join(errors[:3])
            self._proxy_summary.setStyleSheet(f"color: {theme.WARNING};")
        else:
            self._proxy_summary.setStyleSheet(f"color: {theme.SUCCESS};")
        self._proxy_summary.setText(summary)

    def _test_proxies(self) -> None:
        proxies, errors = parse_proxy_list(self._proxy_list.toPlainText().splitlines())
        if not proxies:
            QMessageBox.information(self, "Proxy", "There are no valid proxies to test.")
            return

        self._proxy_results.clear()
        self._proxy_results.show()
        for error in errors:
            self._proxy_results.appendPlainText(f"✗ {error}")
        self._test_button.setEnabled(False)
        self._test_button.setText(f"Testing (0/{len(proxies)})")
        counts = {"done": 0, "ok": 0}

        def run_checks(progress, cancelled) -> None:
            with ThreadPoolExecutor(max_workers=min(10, len(proxies))) as pool:
                futures = [pool.submit(check_proxy, proxy) for proxy in proxies]
                for future in as_completed(futures):
                    progress(future.result(), len(proxies))
                    if cancelled():
                        break

        def on_progress(result: ProxyCheckResult, total: int) -> None:
            counts["done"] += 1
            if result.ok:
                counts["ok"] += 1
                line = f"✓ {result.proxy}  →  {result.ip}  ({result.latency_ms} ms)"
            else:
                line = f"✗ {result.proxy}  →  {result.error}"
            self._proxy_results.appendPlainText(line)
            self._test_button.setText(f"Testing ({counts['done']}/{total})")

        def on_done(*_) -> None:
            self._test_button.setEnabled(True)
            self._test_button.setText("Test proxies")
            self._proxy_results.appendPlainText(
                f"\n{counts['ok']}/{len(proxies)} proxies are working."
            )

        task = run_in_background(run_checks, on_progress=on_progress, on_error=on_done)
        task.succeeded.connect(on_done)

    # ---------------------------------------------------------------- folders
    def _build_folders_group(self) -> QGroupBox:
        group = QGroupBox("Folders")
        layout = QHBoxLayout(group)
        logs = QPushButton("Open logs folder")
        config = QPushButton("Open settings folder")
        logs.clicked.connect(lambda: open_folder(paths.logs_dir()))
        config.clicked.connect(lambda: open_folder(paths.config_dir()))
        layout.addWidget(logs)
        layout.addWidget(config)
        layout.addStretch(1)
        return group

    # ------------------------------------------------------------------- load
    def _load(self) -> None:
        settings = self._context.settings
        self._auto_check.blockSignals(True)
        self._auto_check.setChecked(settings.check_updates_on_startup)
        self._auto_check.blockSignals(False)
        self._proxy_enabled.setChecked(settings.proxy_enabled)
        index = self._rotation.findData(settings.proxy_rotation)
        self._rotation.setCurrentIndex(max(index, 0))
        self._proxy_list.setPlainText("\n".join(settings.proxies))
        if self._context.credentials.get(GITHUB_TOKEN):
            self._set_token_status("A token is saved. Paste a new one to replace it.")
        else:
            self._set_token_status("No token saved.")
