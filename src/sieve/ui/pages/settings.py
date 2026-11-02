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
### GitHub token nasıl oluşturulur?

Sieve, güncellemeleri private `{GITHUB_REPO}` reposundan indirir. Bunun için
**sadece okuma yetkisi olan** bir token yeterlidir.

1. GitHub'da **Settings → Developer settings → Personal access tokens →
   Fine-grained tokens** sayfasına git ve **Generate new token**'a tıkla.
2. **Token name**: örneğin `Sieve updates`.
3. **Expiration**: istediğin bir süre seç. Süresi dolunca yenisini buraya eklemen yeterli.
4. **Repository access**: **Only select repositories** → `{GITHUB_REPO.split('/')[1]}`.
5. **Permissions → Repository permissions → Contents**: **Read-only**.
   (Metadata otomatik olarak Read-only eklenir.)
6. **Generate token**'a tıkla, çıkan değeri kopyalayıp buraya yapıştır.

Token bu bilgisayarda Windows'un kendi şifrelemesiyle (DPAPI) saklanır ve
yalnızca senin Windows kullanıcın tarafından çözülebilir.
"""


class SettingsPage(Page):
    token_changed = Signal()

    def __init__(self, context: AppContext) -> None:
        super().__init__("Ayarlar")
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
        show = QPushButton("Göster")
        show.setCheckable(True)
        show.toggled.connect(
            lambda on: (
                self._token_input.setEchoMode(
                    QLineEdit.EchoMode.Normal if on else QLineEdit.EchoMode.Password
                ),
                show.setText("Gizle" if on else "Göster"),
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
        save = primary_button("Kaydet ve test et")
        remove = QPushButton("Token'ı sil")
        help_button = QPushButton("Token nasıl oluşturulur?")
        save.clicked.connect(self._save_token)
        remove.clicked.connect(self._remove_token)
        help_button.clicked.connect(self._show_token_help)
        buttons.addWidget(save)
        buttons.addWidget(remove)
        buttons.addStretch(1)
        buttons.addWidget(help_button)
        layout.addLayout(buttons)

        self._auto_check = QCheckBox("Açılışta güncellemeleri otomatik kontrol et")
        self._auto_check.toggled.connect(self._save_update_prefs)
        layout.addWidget(self._auto_check)
        return group

    def _set_token_status(self, text: str, color: str = theme.TEXT_MUTED) -> None:
        self._token_status.setText(text)
        self._token_status.setStyleSheet(f"color: {color};")

    def _save_token(self) -> None:
        token = self._token_input.text().strip()
        if not token:
            QMessageBox.information(self, "Token", "Önce token'ı yapıştırmalısın.")
            return
        self._set_token_status("Token test ediliyor...")

        def on_success(repo: str) -> None:
            self._context.credentials.set(GITHUB_TOKEN, token)
            self._token_input.clear()
            self._set_token_status(f"Token kaydedildi. {repo} reposuna erişim var.", theme.SUCCESS)
            self.token_changed.emit()

        def on_error(exc: Exception) -> None:
            message = str(exc) if isinstance(exc, updater.UpdateError) else "Beklenmeyen hata."
            self._set_token_status(f"Token kaydedilmedi: {message}", theme.DANGER)

        run_in_background(updater.verify_token, token, on_success=on_success, on_error=on_error)

    def _remove_token(self) -> None:
        if not self._context.credentials.get(GITHUB_TOKEN):
            return
        answer = QMessageBox.question(
            self, "Token'ı sil", "Kayıtlı GitHub token'ı silinsin mi?"
        )
        if answer == QMessageBox.StandardButton.Yes:
            self._context.credentials.delete(GITHUB_TOKEN)
            self._set_token_status("Kayıtlı token yok.")
            self.token_changed.emit()

    def _show_token_help(self) -> None:
        dialog = QDialog(self)
        dialog.setWindowTitle("GitHub token")
        dialog.resize(560, 460)
        layout = QVBoxLayout(dialog)
        browser = QTextBrowser()
        browser.setMarkdown(TOKEN_HELP)
        layout.addWidget(browser)
        close = QPushButton("Kapat")
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
            "Buradaki proxy listesi proxy destekleyen tüm araçlar tarafından kullanılır. "
            "Her satıra bir proxy: host:port, host:port:user:pass, user:pass@host:port "
            "veya http:// / socks5:// ile başlayan tam adres."
        ))

        self._proxy_enabled = QCheckBox("Proxy kullan")
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
        save = primary_button("Kaydet")
        self._test_button = QPushButton("Proxy'leri test et")
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

        summary = f"{len(proxies)} proxy kaydedildi."
        if errors:
            summary += f" {len(errors)} satır okunamadı: " + "; ".join(errors[:3])
            self._proxy_summary.setStyleSheet(f"color: {theme.WARNING};")
        else:
            self._proxy_summary.setStyleSheet(f"color: {theme.SUCCESS};")
        self._proxy_summary.setText(summary)

    def _test_proxies(self) -> None:
        proxies, errors = parse_proxy_list(self._proxy_list.toPlainText().splitlines())
        if not proxies:
            QMessageBox.information(self, "Proxy", "Test edilecek geçerli proxy yok.")
            return

        self._proxy_results.clear()
        self._proxy_results.show()
        for error in errors:
            self._proxy_results.appendPlainText(f"✗ {error}")
        self._test_button.setEnabled(False)
        self._test_button.setText(f"Test ediliyor (0/{len(proxies)})")
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
            self._test_button.setText(f"Test ediliyor ({counts['done']}/{total})")

        def on_done(*_) -> None:
            self._test_button.setEnabled(True)
            self._test_button.setText("Proxy'leri test et")
            self._proxy_results.appendPlainText(
                f"\n{counts['ok']}/{len(proxies)} proxy çalışıyor."
            )

        task = run_in_background(run_checks, on_progress=on_progress, on_error=on_done)
        task.succeeded.connect(on_done)

    # ---------------------------------------------------------------- folders
    def _build_folders_group(self) -> QGroupBox:
        group = QGroupBox("Klasörler")
        layout = QHBoxLayout(group)
        logs = QPushButton("Log klasörünü aç")
        config = QPushButton("Ayar klasörünü aç")
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
            self._set_token_status("Kayıtlı bir token var. Değiştirmek için yenisini yapıştır.")
        else:
            self._set_token_status("Kayıtlı token yok.")
