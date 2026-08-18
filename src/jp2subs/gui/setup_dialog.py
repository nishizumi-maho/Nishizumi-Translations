"""First-run dialog that installs the pieces the app cannot work without."""
from __future__ import annotations

from PySide6 import QtCore, QtWidgets

from .. import branding
from ..runtime import catalog, store
from ..runtime.manager import manager
from . import icons
from .common import Card, IconButton, StatusChip, hline, label
from .storage import change_location
from .workers import ComponentInstallWorker

#: Offered on first run. The full catalog stays available on the Components page.
STARTER_MODELS = ("model:small", "model:large-v3-turbo", "model:large-v3")


class SetupDialog(QtWidgets.QDialog):
    """Walks a new user through downloading FFmpeg and one speech model."""

    def __init__(self, parent: QtWidgets.QWidget | None = None):
        super().__init__(parent)
        self.setWindowTitle(f"Set up {branding.APP_NAME}")
        self.setModal(True)
        self.resize(660, 620)

        self._queue: list[str] = []
        self._done_mode = False
        self._worker: ComponentInstallWorker | None = None
        self._failed: list[str] = []

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(26, 24, 26, 22)
        layout.setSpacing(18)

        layout.addLayout(self._build_header())

        scroll = QtWidgets.QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        container = QtWidgets.QWidget()
        self._body = QtWidgets.QVBoxLayout(container)
        self._body.setContentsMargins(0, 0, 8, 0)
        self._body.setSpacing(14)
        scroll.setWidget(container)
        layout.addWidget(scroll, 1)

        self._build_location_card()
        self._build_ffmpeg_card()
        self._build_model_card()
        self._body.addStretch(1)

        layout.addWidget(self._build_progress_area())
        layout.addLayout(self._build_buttons())

        self._refresh()

    # -- construction -----------------------------------------------------

    def _build_header(self) -> QtWidgets.QHBoxLayout:
        row = QtWidgets.QHBoxLayout()
        row.setSpacing(14)

        logo = QtWidgets.QLabel()
        logo.setPixmap(icons.app_logo(48))
        logo.setFixedSize(48, 48)
        row.addWidget(logo, 0, QtCore.Qt.AlignTop)

        text = QtWidgets.QVBoxLayout()
        text.setSpacing(3)
        text.addWidget(label(f"Welcome to {branding.APP_NAME}", "PageTitle"))
        text.addWidget(
            label(
                "Two things get downloaded once, then you are set. Pick the drive they "
                "land on below — everything can be moved or removed later.",
                "PageSubtitle",
            )
        )
        row.addLayout(text, 1)
        return row

    def _build_location_card(self) -> None:
        self._location_card = Card(
            "Install location",
            "Models are large. Any drive with room works — it does not have to be the "
            "one the app is installed on.",
            icon_name="folder",
        )
        self._location_value = label("", "CardTitle")
        self._location_card.body.addWidget(self._location_value)
        self._location_hint = label("", "Faint")
        self._location_card.body.addWidget(self._location_hint)

        row = QtWidgets.QHBoxLayout()
        change = IconButton("Change folder", "folder")
        change.clicked.connect(self._change_location)
        row.addWidget(change, 0)
        row.addStretch(1)
        self._location_card.body.addLayout(row)

        self._body.addWidget(self._location_card)

    def _change_location(self) -> None:
        if change_location(self):
            self._refresh()

    def _refresh_location(self) -> None:
        self._location_value.setText(str(store.data_dir()))
        free = store.free_space()
        self._location_hint.setText(
            f"{store.human_size(free)} free on that drive." if free else ""
        )

    def _build_ffmpeg_card(self) -> None:
        component = catalog.ffmpeg_component()
        self._ffmpeg_card = Card(
            "1 · FFmpeg",
            "Extracts audio from video and writes the finished files.",
            icon_name="cpu",
        )
        self._ffmpeg_chip = StatusChip("Not installed", "neutral")
        self._ffmpeg_card.add_header_widget(self._ffmpeg_chip)
        self._ffmpeg_card.body.addWidget(
            label(f"About {store.human_size(component.approx_size)} to download.", "Faint")
        )
        self._body.addWidget(self._ffmpeg_card)

    def _build_model_card(self) -> None:
        self._model_card = Card(
            "2 · Speech model",
            "Bigger models transcribe Japanese more accurately and take longer to run.",
            icon_name="waveform",
        )
        self._model_chip = StatusChip("None installed", "neutral")
        self._model_card.add_header_widget(self._model_chip)

        self._model_group = QtWidgets.QButtonGroup(self)
        self._model_buttons: dict[str, QtWidgets.QRadioButton] = {}

        for index, key in enumerate(STARTER_MODELS):
            component = catalog.component(key)
            if not component:
                continue
            if index:
                self._model_card.body.addWidget(hline())

            row = QtWidgets.QVBoxLayout()
            row.setSpacing(3)

            title_row = QtWidgets.QHBoxLayout()
            title_row.setSpacing(7)
            radio = QtWidgets.QRadioButton(component.name)
            radio.setChecked(component.recommended)
            self._model_group.addButton(radio)
            self._model_buttons[key] = radio
            title_row.addWidget(radio, 0)
            if component.recommended:
                title_row.addWidget(StatusChip("Recommended", "accent"), 0)
            title_row.addWidget(StatusChip(component.quality, "neutral"), 0)
            title_row.addWidget(StatusChip(component.speed, "neutral"), 0)
            title_row.addStretch(1)
            title_row.addWidget(label(store.human_size(component.approx_size), "Faint"), 0)
            row.addLayout(title_row)

            hint = label(component.summary, "CardHint")
            hint.setContentsMargins(24, 0, 0, 0)
            row.addWidget(hint)

            holder = QtWidgets.QWidget()
            holder.setLayout(row)
            self._model_card.body.addWidget(holder)

        self._model_card.body.addWidget(hline())
        self._model_card.body.addWidget(
            label(
                "More models — including Whisper Tiny, Base, Medium and the distilled build — "
                "are on the Components page once the app opens.",
                "Faint",
            )
        )
        self._body.addWidget(self._model_card)

    def _build_progress_area(self) -> QtWidgets.QWidget:
        holder = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(holder)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        self._progress = QtWidgets.QProgressBar()
        self._progress.setObjectName("Slim")
        self._progress.setTextVisible(False)
        self._progress.setVisible(False)
        layout.addWidget(self._progress)

        self._status = label("", "Faint")
        layout.addWidget(self._status)
        return holder

    def _build_buttons(self) -> QtWidgets.QHBoxLayout:
        row = QtWidgets.QHBoxLayout()
        row.setSpacing(9)

        self._skip_btn = QtWidgets.QPushButton("Skip for now")
        self._skip_btn.clicked.connect(self.reject)

        self._cancel_btn = QtWidgets.QPushButton("Cancel download")
        self._cancel_btn.clicked.connect(self._cancel)
        self._cancel_btn.setVisible(False)

        self._install_btn = IconButton("Install and continue", "download", primary=True)
        self._install_btn.setMinimumHeight(38)
        self._install_btn.clicked.connect(self._start)

        row.addWidget(self._skip_btn, 0)
        row.addStretch(1)
        row.addWidget(self._cancel_btn, 0)
        row.addWidget(self._install_btn, 0)
        return row

    # -- state ------------------------------------------------------------

    def _refresh(self) -> None:
        manager.refresh()
        self._refresh_location()

        ffmpeg_ready = manager.is_installed("tool:ffmpeg") or _ffmpeg_on_path()
        self._ffmpeg_chip.set_status(
            "Ready" if ffmpeg_ready else "Not installed",
            "success" if ffmpeg_ready else "neutral",
        )
        self._ffmpeg_card.setEnabled(not ffmpeg_ready)

        installed = manager.installed_models()
        if installed:
            names = ", ".join(item.name for item in installed)
            self._model_chip.set_status(f"Installed: {names}", "success")
        else:
            self._model_chip.set_status("None installed", "neutral")

        # A location change can make installed models appear or disappear, so
        # every row is restated rather than only ever being disabled.
        for key, radio in self._model_buttons.items():
            component = catalog.component(key)
            name = component.name if component else key
            here = manager.is_installed(key)
            radio.setText(f"{name} (installed)" if here else name)
            radio.setEnabled(not here)

        self._set_done_mode(bool(ffmpeg_ready and installed))

    def _set_done_mode(self, done: bool) -> None:
        """Swap the primary button between installing and closing the dialog."""

        if done is self._done_mode:
            return
        self._done_mode = done
        self._install_btn.clicked.disconnect()
        if done:
            self._install_btn.setText("Done")
            self._install_btn.clicked.connect(self.accept)
            self._status.setText("Everything is in place.")
        else:
            self._install_btn.setText("Install and continue")
            self._install_btn.clicked.connect(self._start)
            self._status.setText("")

    def _pending_keys(self) -> list[str]:
        keys: list[str] = []
        if not manager.is_installed("tool:ffmpeg") and not _ffmpeg_on_path():
            keys.append("tool:ffmpeg")
        if not manager.installed_models():
            for key, radio in self._model_buttons.items():
                if radio.isChecked() and radio.isEnabled():
                    keys.append(key)
                    break
        return keys

    # -- install ----------------------------------------------------------

    def _start(self) -> None:
        self._queue = self._pending_keys()
        self._failed = []
        if not self._queue:
            self.accept()
            return

        free = store.free_space()
        needed = sum((catalog.component(key).approx_size for key in self._queue if catalog.component(key)), 0)
        if free and needed and free < needed * 1.15:
            QtWidgets.QMessageBox.warning(
                self,
                "Not enough disk space",
                f"About {store.human_size(needed)} is needed but only {store.human_size(free)} "
                f"is free on the drive holding\n{store.data_dir()}.",
            )
            return

        self._install_btn.setEnabled(False)
        self._skip_btn.setEnabled(False)
        self._cancel_btn.setVisible(True)
        self._cancel_btn.setEnabled(True)
        self._progress.setVisible(True)
        self._install_next()

    def _install_next(self) -> None:
        if not self._queue:
            self._finish()
            return

        key = self._queue.pop(0)
        component = catalog.component(key)
        self._status.setText(f"Downloading {component.name if component else key}...")
        self._progress.setRange(0, 0)

        worker = ComponentInstallWorker(key)
        worker.signals.progress.connect(self._on_progress)
        worker.signals.detail.connect(self._on_detail)
        worker.signals.finished.connect(self._on_one_finished)
        worker.signals.failed.connect(self._on_failed)
        worker.signals.cancelled.connect(self._on_cancelled)
        self._worker = worker
        QtCore.QThreadPool.globalInstance().start(worker)

    def _cancel(self) -> None:
        self._queue = []
        if self._worker:
            self._worker.cancel()
            self._cancel_btn.setEnabled(False)
            self._status.setText("Cancelling...")

    @QtCore.Slot(str, int)
    def _on_progress(self, _key: str, percent: int) -> None:
        if percent < 0:
            self._progress.setRange(0, 0)
        else:
            self._progress.setRange(0, 100)
            self._progress.setValue(percent)

    @QtCore.Slot(str, str)
    def _on_detail(self, key: str, detail: str) -> None:
        component = catalog.component(key)
        name = component.name if component else key
        self._status.setText(f"{name} · {detail}")

    @QtCore.Slot(str)
    def _on_one_finished(self, _key: str) -> None:
        self._worker = None
        self._install_next()

    @QtCore.Slot(str, str)
    def _on_failed(self, key: str, message: str) -> None:
        self._worker = None
        component = catalog.component(key)
        self._failed.append(f"{component.name if component else key}: {message}")
        self._install_next()

    @QtCore.Slot(str)
    def _on_cancelled(self, _key: str) -> None:
        self._worker = None
        self._reset_controls()
        self._status.setText("Download cancelled.")

    def _finish(self) -> None:
        self._reset_controls()
        manager.refresh()

        if self._failed:
            QtWidgets.QMessageBox.warning(
                self,
                "Some downloads did not finish",
                "\n\n".join(self._failed)
                + "\n\nYou can retry from the Components page inside the app.",
            )
            self._refresh()
            return

        self._status.setText("Setup complete.")
        self.accept()

    def _reset_controls(self) -> None:
        self._progress.setVisible(False)
        self._progress.setRange(0, 100)
        self._install_btn.setEnabled(True)
        self._skip_btn.setEnabled(True)
        self._cancel_btn.setVisible(False)

    def closeEvent(self, event) -> None:  # noqa: N802
        if self._worker:
            self._worker.cancel()
        super().closeEvent(event)


def _ffmpeg_on_path() -> bool:
    import shutil

    return shutil.which("ffmpeg") is not None
