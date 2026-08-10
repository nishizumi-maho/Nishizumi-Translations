"""Components page: one-click download and removal of models and tools."""
from __future__ import annotations

from PySide6 import QtCore, QtWidgets

from ...runtime import catalog, store
from ...runtime.catalog import Component, ComponentKind
from ...runtime.manager import manager
from ..common import Banner, Card, IconButton, ScrollPage, StatusChip, hline, label, reveal
from ..workers import ComponentInstallWorker


class ComponentRow(QtWidgets.QFrame):
    """One installable item: description, size, status and action buttons."""

    changed = QtCore.Signal()
    install_started = QtCore.Signal(str)

    def __init__(self, component: Component, parent: QtWidgets.QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("Inset")
        self.component = component
        self._worker: ComponentInstallWorker | None = None

        outer = QtWidgets.QVBoxLayout(self)
        outer.setContentsMargins(15, 13, 15, 13)
        outer.setSpacing(9)

        top = QtWidgets.QHBoxLayout()
        top.setSpacing(11)

        text_box = QtWidgets.QVBoxLayout()
        text_box.setSpacing(5)

        title_row = QtWidgets.QHBoxLayout()
        title_row.setSpacing(7)
        title_row.addWidget(label(component.name, "CardTitle"), 0)

        self.status_chip = StatusChip("Not installed", "neutral")
        title_row.addWidget(self.status_chip, 0)

        for text, tone in self._trait_chips():
            title_row.addWidget(StatusChip(text, tone), 0)
        title_row.addStretch(1)
        text_box.addLayout(title_row)

        text_box.addWidget(label(component.summary, "CardHint"))
        if component.notes:
            text_box.addWidget(label(component.notes, "Faint"))

        self.size_label = label("", "Faint")
        text_box.addWidget(self.size_label)
        top.addLayout(text_box, 1)

        buttons = QtWidgets.QVBoxLayout()
        buttons.setSpacing(6)
        buttons.setAlignment(QtCore.Qt.AlignTop)

        self.install_btn = QtWidgets.QPushButton("Install")
        self.install_btn.setObjectName("Primary")
        self.install_btn.setMinimumWidth(112)
        self.install_btn.clicked.connect(self.start_install)
        buttons.addWidget(self.install_btn)

        self.cancel_btn = QtWidgets.QPushButton("Cancel")
        self.cancel_btn.setMinimumWidth(112)
        self.cancel_btn.clicked.connect(self._cancel)
        self.cancel_btn.setVisible(False)
        buttons.addWidget(self.cancel_btn)

        self.remove_btn = QtWidgets.QPushButton("Remove")
        self.remove_btn.setObjectName("Danger")
        self.remove_btn.setMinimumWidth(112)
        self.remove_btn.clicked.connect(self._remove)
        self.remove_btn.setVisible(False)
        buttons.addWidget(self.remove_btn)

        top.addLayout(buttons, 0)
        outer.addLayout(top)

        self.progress = QtWidgets.QProgressBar()
        self.progress.setObjectName("Slim")
        self.progress.setTextVisible(False)
        self.progress.setVisible(False)
        outer.addWidget(self.progress)

        self.detail_label = label("", "Faint")
        self.detail_label.setVisible(False)
        outer.addWidget(self.detail_label)

        self.refresh()

    # -- presentation -----------------------------------------------------

    def _trait_chips(self) -> list[tuple[str, str]]:
        chips: list[tuple[str, str]] = []
        if self.component.recommended:
            chips.append(("Recommended", "accent"))
        if self.component.required:
            chips.append(("Required", "warning"))
        if self.component.quality:
            chips.append((self.component.quality, "neutral"))
        if self.component.speed:
            chips.append((self.component.speed, "neutral"))
        return chips

    def refresh(self) -> None:
        if self._worker is not None:
            return
        status = manager.status(self.component.key)
        installed = bool(status and status.installed)

        if installed:
            self.status_chip.set_status("Installed", "success")
            on_disk = store.human_size(status.size) if status else "—"
            version = f" · {status.version}" if status and status.version else ""
            self.size_label.setText(f"{on_disk} on disk{version}")
        else:
            self.status_chip.set_status("Not installed", "neutral")
            self.size_label.setText(f"About {store.human_size(self.component.approx_size)} to download")

        self.install_btn.setVisible(not installed)
        self.remove_btn.setVisible(installed)
        self.cancel_btn.setVisible(False)
        self.progress.setVisible(False)
        self.detail_label.setVisible(False)

    def set_busy(self, busy: bool) -> None:
        """Disable the buttons while another component is installing."""

        if self._worker is not None:
            return
        self.install_btn.setEnabled(not busy)
        self.remove_btn.setEnabled(not busy)

    # -- actions ----------------------------------------------------------

    def start_install(self) -> None:
        if self._worker is not None:
            return
        free = store.free_space()
        if free and self.component.approx_size and free < self.component.approx_size * 1.15:
            QtWidgets.QMessageBox.warning(
                self,
                "Not enough disk space",
                f"{self.component.name} needs roughly "
                f"{store.human_size(self.component.approx_size)} but only "
                f"{store.human_size(free)} is free on the drive holding\n{store.data_dir()}.",
            )
            return

        self._worker = ComponentInstallWorker(self.component.key)
        self._worker.signals.progress.connect(self._on_progress)
        self._worker.signals.detail.connect(self._on_detail)
        self._worker.signals.finished.connect(self._on_finished)
        self._worker.signals.failed.connect(self._on_failed)
        self._worker.signals.cancelled.connect(self._on_cancelled)

        self.status_chip.set_status("Installing", "accent")
        self.install_btn.setVisible(False)
        self.remove_btn.setVisible(False)
        self.cancel_btn.setVisible(True)
        self.progress.setVisible(True)
        self.progress.setRange(0, 0)
        self.detail_label.setVisible(True)
        self.detail_label.setText("Starting download...")

        self.install_started.emit(self.component.key)
        QtCore.QThreadPool.globalInstance().start(self._worker)

    def _cancel(self) -> None:
        if self._worker:
            self._worker.cancel()
            self.detail_label.setText("Cancelling...")
            self.cancel_btn.setEnabled(False)

    def _remove(self) -> None:
        answer = QtWidgets.QMessageBox.question(
            self,
            f"Remove {self.component.name}?",
            f"This deletes the downloaded files from\n{manager.install_path(self.component)}\n\n"
            "You can install it again at any time.",
            QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No,
            QtWidgets.QMessageBox.No,
        )
        if answer != QtWidgets.QMessageBox.Yes:
            return
        manager.uninstall(self.component.key)
        self.refresh()
        self.changed.emit()

    # -- worker callbacks -------------------------------------------------

    @QtCore.Slot(str, int)
    def _on_progress(self, _key: str, percent: int) -> None:
        if percent < 0:
            self.progress.setRange(0, 0)
        else:
            self.progress.setRange(0, 100)
            self.progress.setValue(percent)

    @QtCore.Slot(str, str)
    def _on_detail(self, _key: str, detail: str) -> None:
        self.detail_label.setText(detail)

    def _finish(self) -> None:
        self._worker = None
        self.cancel_btn.setEnabled(True)
        self.install_btn.setEnabled(True)
        self.remove_btn.setEnabled(True)
        self.refresh()
        self.changed.emit()

    @QtCore.Slot(str)
    def _on_finished(self, _key: str) -> None:
        self._finish()

    @QtCore.Slot(str)
    def _on_cancelled(self, _key: str) -> None:
        self._finish()

    @QtCore.Slot(str, str)
    def _on_failed(self, _key: str, message: str) -> None:
        self._finish()
        QtWidgets.QMessageBox.critical(
            self,
            f"Could not install {self.component.name}",
            f"{message}\n\nCheck your internet connection and try again.",
        )


class ComponentsPage(ScrollPage):
    """Everything the app can fetch on the user's behalf, in one place."""

    components_changed = QtCore.Signal()

    def __init__(self, parent: QtWidgets.QWidget | None = None):
        super().__init__(
            "Components",
            "Models and tools download straight into the app. Nothing to install by hand.",
            parent,
        )
        self._rows: list[ComponentRow] = []

        folder_btn = IconButton("Open folder", "folder")
        folder_btn.clicked.connect(lambda: reveal(store.data_dir()))
        self.header.add_action(folder_btn)

        refresh_btn = IconButton("Refresh", "refresh")
        refresh_btn.clicked.connect(self.refresh)
        self.header.add_action(refresh_btn)

        self.summary_banner = Banner("", "accent")
        self.content.addWidget(self.summary_banner)

        self._add_section(
            "Required",
            "FFmpeg does the audio extraction, muxing and burn-in.",
            "cpu",
            [item for item in catalog.all_components() if item.kind is ComponentKind.TOOL],
        )
        self._add_section(
            "Speech models",
            "Pick one to start. Bigger models are more accurate and slower; you can keep several.",
            "waveform",
            list(catalog.models()),
        )
        acceleration = [item for item in catalog.all_components() if item.kind is ComponentKind.ACCELERATION]
        if acceleration:
            self._add_section(
                "GPU acceleration",
                "Optional. Speeds transcription up dramatically on an NVIDIA card.",
                "spark",
                acceleration,
            )

        self.content.addStretch(1)
        self.refresh()

    def _add_section(self, title: str, hint: str, icon_name: str, items: list[Component]) -> None:
        if not items:
            return
        card = Card(title, hint, icon_name=icon_name)
        for index, item in enumerate(items):
            if index:
                card.body.addWidget(hline())
            row = ComponentRow(item)
            row.changed.connect(self._on_row_changed)
            row.install_started.connect(self._on_install_started)
            card.body.addWidget(row)
            self._rows.append(row)
        self.content.addWidget(card)

    def _on_install_started(self, _key: str) -> None:
        for row in self._rows:
            row.set_busy(True)

    def _on_row_changed(self) -> None:
        for row in self._rows:
            row.set_busy(False)
        manager.refresh()
        self._update_summary()
        self.components_changed.emit()

    def refresh(self) -> None:
        manager.refresh()
        for row in self._rows:
            row.refresh()
        self._update_summary()

    def _update_summary(self) -> None:
        used = store.human_size(manager.total_size())
        free = store.human_size(store.free_space())
        installed = len(manager.installed_models())

        if manager.is_ready():
            self.summary_banner.set_message(
                f"Ready to transcribe · {installed} model(s) installed · "
                f"{used} used, {free} free in {store.data_dir()}",
                "success",
                "",
            )
        else:
            missing = ", ".join(item.name for item in manager.missing_required())
            self.summary_banner.set_message(
                f"Still needed: {missing}. Install below and the app is ready to go.",
                "warning",
                "",
            )
