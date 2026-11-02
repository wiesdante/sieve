"""About page: version, author and manual update check."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton, QVBoxLayout

from sieve import AUTHOR, GITHUB_REPO, __version__, paths
from sieve.ui.updates import UpdateController
from sieve.ui.widgets import Page, muted_label, open_url, primary_button


class AboutPage(Page):
    def __init__(self, updates: UpdateController) -> None:
        super().__init__("About")
        self._updates = updates

        card = QFrame()
        card.setObjectName("Card")
        row = QHBoxLayout(card)
        row.setContentsMargins(20, 20, 20, 20)
        row.setSpacing(18)

        logo = QLabel()
        pixmap = QPixmap(str(paths.resource_path("assets", "icon.png")))
        if not pixmap.isNull():
            logo.setPixmap(
                pixmap.scaled(
                    84, 84,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
            )
        row.addWidget(logo, 0, Qt.AlignmentFlag.AlignTop)

        info = QVBoxLayout()
        name = QLabel("Sieve")
        name.setObjectName("PageTitle")
        info.addWidget(name)
        info.addWidget(muted_label(f"Version {__version__}  ·  by {AUTHOR}"))
        info.addSpacing(6)
        info.addWidget(QLabel(
            "A desktop toolkit that brings data scraping workflows together in one app."
        ))
        info.addStretch(1)
        row.addLayout(info, 1)
        self.content.addWidget(card)

        update_card = QFrame()
        update_card.setObjectName("Card")
        update_layout = QVBoxLayout(update_card)
        update_layout.setContentsMargins(20, 16, 20, 16)
        heading = QLabel("Updates")
        heading.setStyleSheet("font-weight: 600;")
        update_layout.addWidget(heading)
        self._status = muted_label(updates.status or "Not checked yet.")
        update_layout.addWidget(self._status)

        buttons = QHBoxLayout()
        check = primary_button("Check for updates")
        releases = QPushButton("Open releases page")
        check.clicked.connect(lambda: self._updates.check(manual=True))
        releases.clicked.connect(lambda: open_url(f"https://github.com/{GITHUB_REPO}/releases"))
        buttons.addWidget(check)
        buttons.addWidget(releases)
        buttons.addStretch(1)
        update_layout.addLayout(buttons)
        self.content.addWidget(update_card)

        updates.status_changed.connect(self._status.setText)
        self.finish()
