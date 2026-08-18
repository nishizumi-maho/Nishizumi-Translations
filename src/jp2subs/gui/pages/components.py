"""Components page: one-click download and removal of models and tools."""
from __future__ import annotations

from PySide6 import QtCore, QtWidgets

from ...runtime import catalog, store
from ...runtime.catalog import Component, ComponentKind
from ...runtime.manager import manager
from ..common import Banner, Card, IconButton, ScrollPage, StatusChip, hline, label, reveal
from ..storage import change_location
from ..workers import ComponentInstallWorker, ModelSearchWorker


class ComponentRow(QtWidgets.QFrame):
    """One installable item: description, size, status and action buttons."""

    changed = QtCore.Signal()
    install_started = QtCore.Signal(str)

    def __init__(
        self,
        component: Component,
        parent: QtWidgets.QWidget | None = None,
        *,
        removable: bool = True,
    ):
        super().__init__(parent)
        self.setObjectName("Inset")
        self.component = component
        self._removable = removable
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
        self.remove_btn.setVisible(installed and self._removable)
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

        self._worker = ComponentInstallWorker(
            self.component.key, component=self.component if self.component.custom else None
        )
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


_FAMILY_HINTS = {
    "General purpose": "Official multilingual Whisper builds. Bigger is more accurate and slower.",
    "Tuned for Japanese": "Fine-tuned on Japanese speech. Usually beat a general model of the same size.",
    "Downloaded from Hugging Face": "Models you installed through search.",
}


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
        self._search_rows: list[ComponentRow] = []
        self._custom_rows: list[ComponentRow] = []
        self._installed_card: Card | None = None

        folder_btn = IconButton("Open folder", "folder")
        folder_btn.clicked.connect(lambda: reveal(store.data_dir()))
        self.header.add_action(folder_btn)

        location_btn = IconButton("Change location", "sliders")
        location_btn.setToolTip("Install models and tools on another drive.")
        location_btn.clicked.connect(self._change_location)
        self.header.add_action(location_btn)

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

        for family, items in catalog.models_by_family().items():
            self._add_section(
                f"Speech models · {family.value}",
                _FAMILY_HINTS.get(family.value, ""),
                "waveform",
                list(items),
            )

        self._build_search_card()
        self._build_installed_custom_card()

        self._add_section(
            "Subtitle translation",
            "Translate finished subtitles into other languages without sending anything online.",
            "external",
            list(catalog.translation_models()),
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

    # -- Hugging Face search ---------------------------------------------

    def _build_search_card(self) -> None:
        card = Card(
            "Find another model",
            "Search Hugging Face for any Whisper model in CTranslate2 format — including ones "
            "released after this app was built.",
            icon_name="download",
        )

        row = QtWidgets.QHBoxLayout()
        row.setSpacing(8)
        self.search_edit = QtWidgets.QLineEdit()
        self.search_edit.setPlaceholderText("e.g. kotoba-whisper, anime, or paste an owner/model id")
        self.search_edit.returnPressed.connect(self._run_search)
        self.search_btn = IconButton("Search", "refresh", primary=True)
        self.search_btn.clicked.connect(self._run_search)
        row.addWidget(self.search_edit, 1)
        row.addWidget(self.search_btn, 0)
        card.body.addLayout(row)

        suggestions = QtWidgets.QHBoxLayout()
        suggestions.setSpacing(6)
        suggestions.addWidget(label("Try:", "Faint"), 0)
        for term in ("whisper japanese", "kotoba-whisper", "faster-whisper turbo", "whisper anime"):
            chip = QtWidgets.QPushButton(term)
            chip.setObjectName("Ghost")
            chip.setCursor(QtCore.Qt.PointingHandCursor)
            chip.clicked.connect(lambda _checked=False, value=term: self._search_for(value))
            suggestions.addWidget(chip, 0)
        suggestions.addStretch(1)
        card.body.addLayout(suggestions)

        self.search_status = label("", "Faint")
        self.search_status.setVisible(False)
        card.body.addWidget(self.search_status)

        self.search_results_box = QtWidgets.QVBoxLayout()
        self.search_results_box.setSpacing(10)
        card.body.addLayout(self.search_results_box)

        self.content.addWidget(card)

    def _build_installed_custom_card(self) -> None:
        """Holds models installed through search, so they can be removed again."""

        self._installed_card = Card(
            "Installed from search",
            "Models you added yourself. They appear in the model picker like any other.",
            icon_name="check",
        )
        self._installed_rows_box = QtWidgets.QVBoxLayout()
        self._installed_rows_box.setSpacing(10)
        self._installed_card.body.addLayout(self._installed_rows_box)
        self._installed_card.setVisible(False)
        self.content.addWidget(self._installed_card)

    def _refresh_installed_custom(self) -> None:
        for row in self._custom_rows:
            if row in self._rows:
                self._rows.remove(row)
            row.setParent(None)
            row.deleteLater()
        self._custom_rows = []

        # Anything currently on screen in the search results already offers a
        # Remove button, so listing it twice would just be noise.
        on_screen = {row.component.key for row in self._search_rows}
        installed = [
            item
            for item in manager.custom_components()
            if manager.is_installed(item.key) and item.key not in on_screen
        ]
        for item in installed:
            row = ComponentRow(item)
            row.changed.connect(self._on_row_changed)
            row.install_started.connect(self._on_install_started)
            self._installed_rows_box.addWidget(row)
            self._custom_rows.append(row)
            self._rows.append(row)

        if self._installed_card:
            self._installed_card.setVisible(bool(installed))

    def _search_for(self, term: str) -> None:
        self.search_edit.setText(term)
        self._run_search()

    def _run_search(self) -> None:
        query = self.search_edit.text().strip()
        self._clear_search_results()
        self.search_status.setVisible(True)
        self.search_status.setText("Searching Hugging Face...")
        self.search_btn.setEnabled(False)

        worker = ModelSearchWorker(query or "faster-whisper")
        worker.signals.results.connect(self._on_search_results)
        worker.signals.failed.connect(self._on_search_failed)
        QtCore.QThreadPool.globalInstance().start(worker)

    def _clear_search_results(self) -> None:
        for row in self._search_rows:
            if row in self._rows:
                self._rows.remove(row)
            row.setParent(None)
            row.deleteLater()
        self._search_rows = []

    @QtCore.Slot(list)
    def _on_search_results(self, results: list) -> None:
        self.search_btn.setEnabled(True)
        if not results:
            self.search_status.setText(
                "Nothing usable found. CTranslate2 builds usually have 'faster-whisper' or 'ct2' in the name."
            )
            return

        self.search_status.setText(f"{len(results)} usable model(s). These install like any other component.")
        for result in results:
            component = catalog.custom_model(
                result.repo_id, approx_size=result.size, name=result.repo_id
            )
            row = ComponentRow(component)
            row.size_label.setText(
                f"About {store.human_size(result.size)} · {result.downloads:,} downloads"
                if result.size
                else f"{result.downloads:,} downloads"
            )
            row.changed.connect(self._on_row_changed)
            row.install_started.connect(self._on_install_started)
            self.search_results_box.addWidget(row)
            self._search_rows.append(row)
            self._rows.append(row)

    def _on_search_failed(self, message: str) -> None:
        self.search_btn.setEnabled(True)
        self.search_status.setText(f"Search failed: {message}")

    def _on_install_started(self, _key: str) -> None:
        for row in self._rows:
            row.set_busy(True)

    def _on_row_changed(self) -> None:
        for row in self._rows:
            row.set_busy(False)
        manager.refresh()
        self._refresh_installed_custom()
        self._update_summary()
        self.components_changed.emit()

    def _change_location(self) -> None:
        if change_location(self):
            self.refresh()
            self.components_changed.emit()

    def refresh(self) -> None:
        manager.refresh()
        self._refresh_installed_custom()
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
