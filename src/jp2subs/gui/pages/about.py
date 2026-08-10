"""About page, which is also where updates are checked and installed."""
from __future__ import annotations

from pathlib import Path

from PySide6 import QtCore, QtGui, QtWidgets

from ... import branding
from ...runtime import store, updater
from ...runtime.manager import manager
from .. import icons
from ..common import Banner, Card, IconButton, ScrollPage, label, reveal
from ..state import load_app_state, persist_app_state
from ..workers import UpdateCheckWorker, UpdateDownloadWorker


class AboutPage(ScrollPage):
    """Version, links, and the whole check/download/install update flow."""

    #: Emitted with a ReleaseInfo when a check finds a newer version.
    update_available = QtCore.Signal(object)

    def __init__(self, parent: QtWidgets.QWidget | None = None):
        super().__init__("About", branding.APP_TAGLINE, parent)
        self._release: updater.ReleaseInfo | None = None
        self._download_worker: UpdateDownloadWorker | None = None
        self._installer_path: Path | None = None

        self._build_identity_card()
        self._build_update_card()
        self._build_links_card()
        self._build_storage_card()
        self.content.addStretch(1)

    # -- construction -----------------------------------------------------

    def _build_identity_card(self) -> None:
        card = Card()
        row = QtWidgets.QHBoxLayout()
        row.setSpacing(16)

        self._logo = QtWidgets.QLabel()
        self._logo.setPixmap(icons.app_logo(56))
        self._logo.setFixedSize(56, 56)
        row.addWidget(self._logo, 0, QtCore.Qt.AlignTop)

        text = QtWidgets.QVBoxLayout()
        text.setSpacing(4)
        text.addWidget(label(branding.APP_NAME, "PageTitle"))
        text.addWidget(label(f"Version {branding.VERSION}", "CardHint"))
        text.addWidget(
            label(
                "Transcribes Japanese speech with Whisper, adds optional romaji, exports "
                "SRT/VTT/ASS, and muxes or burns the result into video with FFmpeg.",
                "CardHint",
            )
        )
        row.addLayout(text, 1)
        card.body.addLayout(row)
        self.content.addWidget(card)

    def _build_update_card(self) -> None:
        card = Card("Updates", "", icon_name="download")

        self.update_banner = Banner("Checking for updates has not run yet.", "accent")
        card.body.addWidget(self.update_banner)

        self.notes_view = QtWidgets.QTextEdit()
        self.notes_view.setReadOnly(True)
        self.notes_view.setMaximumHeight(180)
        self.notes_view.setVisible(False)
        card.body.addWidget(self.notes_view)

        self.update_progress = QtWidgets.QProgressBar()
        self.update_progress.setObjectName("Slim")
        self.update_progress.setTextVisible(False)
        self.update_progress.setVisible(False)
        card.body.addWidget(self.update_progress)

        self.update_detail = label("", "Faint")
        self.update_detail.setVisible(False)
        card.body.addWidget(self.update_detail)

        row = QtWidgets.QHBoxLayout()
        row.setSpacing(9)

        self.check_btn = IconButton("Check for updates", "refresh")
        self.check_btn.clicked.connect(lambda: self.check_for_updates(silent=False))
        row.addWidget(self.check_btn, 0)

        self.download_btn = IconButton("Download and install", "download", primary=True)
        self.download_btn.clicked.connect(self._download_update)
        self.download_btn.setVisible(False)
        row.addWidget(self.download_btn, 0)

        self.install_btn = IconButton("Install now", "check", primary=True)
        self.install_btn.clicked.connect(self._run_installer)
        self.install_btn.setVisible(False)
        row.addWidget(self.install_btn, 0)

        self.release_page_btn = QtWidgets.QPushButton("Open release page")
        self.release_page_btn.clicked.connect(self._open_release_page)
        self.release_page_btn.setVisible(False)
        row.addWidget(self.release_page_btn, 0)

        row.addStretch(1)
        card.body.addLayout(row)

        self.content.addWidget(card)

    def _build_links_card(self) -> None:
        card = Card("Project", "", icon_name="external")
        row = QtWidgets.QHBoxLayout()
        row.setSpacing(9)
        for text, url in (
            ("Source code", branding.REPO_URL),
            ("Documentation", branding.DOCS_URL),
            ("Report an issue", branding.ISSUES_URL),
            ("All releases", branding.RELEASES_URL),
        ):
            button = QtWidgets.QPushButton(text)
            button.clicked.connect(lambda _checked=False, target=url: QtGui.QDesktopServices.openUrl(QtCore.QUrl(target)))
            row.addWidget(button, 0)
        row.addStretch(1)
        card.body.addLayout(row)

        card.body.addWidget(
            label(
                "MIT licensed. Built with PySide6, faster-whisper (CTranslate2), pykakasi and FFmpeg. "
                "Whisper models come from the Systran and Mobius Labs conversions on Hugging Face.",
                "Faint",
            )
        )
        self.content.addWidget(card)

    def _build_storage_card(self) -> None:
        card = Card("Storage", "", icon_name="folder")
        self.storage_label = label("", "CardHint")
        card.body.addWidget(self.storage_label)

        row = QtWidgets.QHBoxLayout()
        open_btn = IconButton("Open data folder", "folder")
        open_btn.clicked.connect(lambda: reveal(store.data_dir()))
        row.addWidget(open_btn, 0)
        row.addStretch(1)
        card.body.addLayout(row)

        self.content.addWidget(card)
        self.refresh_components()

    # -- storage ----------------------------------------------------------

    def refresh_components(self) -> None:
        manager.refresh()
        models = len(manager.installed_models())
        total = manager.total_size()
        self.storage_label.setText(
            f"{store.human_size(total)} of models and tools are installed "
            f"({models} model(s)), in {store.data_dir()}"
            if total
            else f"Nothing downloaded yet. Components will go to {store.data_dir()}"
        )

    # -- update flow ------------------------------------------------------

    def check_for_updates(self, *, silent: bool = False) -> None:
        """Ask GitHub for a newer release. ``silent`` hides 'already current'."""

        cfg = load_app_state()
        self.check_btn.setEnabled(False)
        if not silent:
            self.update_banner.set_message("Checking for updates...", "accent", "")

        worker = UpdateCheckWorker(include_prerelease=cfg.app.include_prereleases)
        worker.signals.checked.connect(lambda release: self._on_checked(release, silent))
        worker.signals.failed.connect(lambda message: self._on_check_failed(message, silent))
        QtCore.QThreadPool.globalInstance().start(worker)

    def _on_checked(self, release: object, silent: bool) -> None:
        self.check_btn.setEnabled(True)
        self._remember_check_time()

        if release is None:
            self._release = None
            self.download_btn.setVisible(False)
            self.install_btn.setVisible(False)
            self.release_page_btn.setVisible(False)
            self.notes_view.setVisible(False)
            if not silent:
                self.update_banner.set_message(
                    f"You are on the latest version ({branding.VERSION}).", "success", ""
                )
            return

        self._release = release
        self.update_available.emit(release)
        self.update_banner.set_message(
            f"Version {release.version} is available. You have {branding.VERSION}.", "accent", ""
        )

        if release.notes:
            self.notes_view.setPlainText(release.notes)
            self.notes_view.setVisible(True)

        self.release_page_btn.setVisible(True)
        if release.has_installer:
            size = store.human_size(release.asset_size)
            self.download_btn.setText(f"Download and install ({size})")
            self.download_btn.setVisible(True)
        else:
            self.download_btn.setVisible(False)
            self.update_banner.set_message(
                f"Version {release.version} is available, but it has no installer for this platform. "
                "Grab it from the release page.",
                "warning",
                "",
            )

    def _on_check_failed(self, message: str, silent: bool) -> None:
        self.check_btn.setEnabled(True)
        if silent:
            return
        self.update_banner.set_message(f"Could not check for updates: {message}", "danger", "")

    def _remember_check_time(self) -> None:
        from datetime import datetime, timezone

        cfg = load_app_state()
        cfg.app.last_update_check = datetime.now(timezone.utc).isoformat(timespec="seconds")
        persist_app_state(cfg)

    def _download_update(self) -> None:
        if not self._release:
            return
        self.download_btn.setEnabled(False)
        self.update_progress.setVisible(True)
        self.update_progress.setRange(0, 0)
        self.update_detail.setVisible(True)
        self.update_detail.setText("Starting download...")

        worker = UpdateDownloadWorker(self._release)
        worker.signals.progress.connect(self._on_download_progress)
        worker.signals.detail.connect(self.update_detail.setText)
        worker.signals.downloaded.connect(self._on_downloaded)
        worker.signals.failed.connect(self._on_download_failed)
        self._download_worker = worker
        QtCore.QThreadPool.globalInstance().start(worker)

    @QtCore.Slot(int)
    def _on_download_progress(self, percent: int) -> None:
        if percent < 0:
            self.update_progress.setRange(0, 0)
        else:
            self.update_progress.setRange(0, 100)
            self.update_progress.setValue(percent)

    @QtCore.Slot(str)
    def _on_downloaded(self, path: str) -> None:
        self._download_worker = None
        self._installer_path = Path(path)
        self.update_progress.setVisible(False)
        self.update_detail.setText(f"Downloaded to {path}")
        self.download_btn.setVisible(False)
        self.install_btn.setVisible(True)
        self.update_banner.set_message(
            "The update is ready. Installing will close the app and run the installer.", "accent", ""
        )

    def _on_download_failed(self, message: str) -> None:
        self._download_worker = None
        self.download_btn.setEnabled(True)
        self.update_progress.setVisible(False)
        self.update_detail.setText("")
        QtWidgets.QMessageBox.critical(self, "Download failed", message)

    def _run_installer(self) -> None:
        if not self._installer_path:
            return
        answer = QtWidgets.QMessageBox.question(
            self,
            "Install the update?",
            f"{branding.APP_NAME} will close so the installer can replace it.\n\n"
            f"{self._installer_path.name}",
            QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No,
            QtWidgets.QMessageBox.Yes,
        )
        if answer != QtWidgets.QMessageBox.Yes:
            return
        try:
            updater.launch_installer(self._installer_path)
        except Exception as exc:  # noqa: BLE001
            QtWidgets.QMessageBox.critical(self, "Could not start the installer", str(exc))
            return
        QtWidgets.QApplication.quit()

    def _open_release_page(self) -> None:
        target = self._release.html_url if self._release else branding.RELEASES_URL
        QtGui.QDesktopServices.openUrl(QtCore.QUrl(target))

    def retheme(self) -> None:
        self._logo.setPixmap(icons.app_logo(56))
