"""Widgets specific to this app.

Everything generic — cards, chips, banners, the file queue, the palette — is
borrowed from the subtitle app's toolkit. What lives here either speaks
Portuguese or knows about components.
"""
from __future__ import annotations

from pathlib import Path

from jp2subs.gui import icons, theme
from jp2subs.gui.common import Card, IconButton, StatusChip, label
from PySide6 import QtCore, QtGui, QtWidgets

from ..components import Component, human_size
from ..media import MEDIA_SUFFIXES
from .workers import ComponentInstallWorker

MEDIA_FILTER = "Áudio e vídeo (" + " ".join(f"*{suffix}" for suffix in sorted(MEDIA_SUFFIXES)) + ");;Todos os arquivos (*)"


def browse_recordings(parent: QtWidgets.QWidget) -> list[str]:
    paths, _filter = QtWidgets.QFileDialog.getOpenFileNames(
        parent, "Escolher a gravação da reunião", "", MEDIA_FILTER
    )
    return paths


class DropZone(QtWidgets.QFrame):
    """Dashed target that takes a dropped recording."""

    files_dropped = QtCore.Signal(list)
    browse_requested = QtCore.Signal()

    def __init__(self, parent: QtWidgets.QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("DropZone")
        self.setAcceptDrops(True)
        self.setCursor(QtCore.Qt.PointingHandCursor)
        self.setMinimumHeight(132)
        self._hover = False

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(6)
        layout.setAlignment(QtCore.Qt.AlignCenter)

        self._icon = QtWidgets.QLabel()
        self._icon.setAlignment(QtCore.Qt.AlignCenter)
        layout.addWidget(self._icon)

        title = label("Arraste aqui a gravação da reunião", "CardTitle")
        title.setAlignment(QtCore.Qt.AlignCenter)
        layout.addWidget(title)

        hint = label("mp3 · m4a · wav · flac · ogg · opus · mp4 · mkv · mov · avi", "Faint")
        hint.setAlignment(QtCore.Qt.AlignCenter)
        layout.addWidget(hint)

        row = QtWidgets.QHBoxLayout()
        row.addStretch(1)
        button = QtWidgets.QPushButton("Escolher arquivo")
        button.clicked.connect(self.browse_requested)
        row.addWidget(button)
        row.addStretch(1)
        layout.addLayout(row)

        self.retheme()

    def retheme(self) -> None:
        colors = theme.active_palette()
        border = colors.accent if self._hover else colors.border_strong
        background = colors.accent_soft if self._hover else colors.surface_alt
        # QLabel derives from QFrame, so the selector has to name this widget or
        # every child label picks up the dashed border too.
        self.setStyleSheet(
            f"QFrame#DropZone {{ border: 2px dashed {border}; border-radius: 13px;"
            f" background-color: {background}; }}"
        )
        self._icon.setPixmap(
            icons.pixmap("waveform", 30, colors.accent if self._hover else colors.text_faint)
        )

    def dragEnterEvent(self, event: QtGui.QDragEnterEvent) -> None:  # noqa: N802
        if event.mimeData().hasUrls():
            self._hover = True
            self.retheme()
            event.acceptProposedAction()

    def dragLeaveEvent(self, event: QtCore.QEvent) -> None:  # noqa: N802
        self._hover = False
        self.retheme()
        super().dragLeaveEvent(event)

    def dropEvent(self, event: QtGui.QDropEvent) -> None:  # noqa: N802
        self._hover = False
        self.retheme()
        paths = [url.toLocalFile() for url in event.mimeData().urls() if url.isLocalFile()]
        if paths:
            self.files_dropped.emit(paths)
            event.acceptProposedAction()

    def mousePressEvent(self, event: QtGui.QMouseEvent) -> None:  # noqa: N802
        if event.button() == QtCore.Qt.LeftButton:
            self.browse_requested.emit()
        super().mousePressEvent(event)


class ComponentRow(QtWidgets.QFrame):
    """One downloadable item: what it is, how big it is, and a button."""

    changed = QtCore.Signal()

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
        self.status_chip = StatusChip("Não instalado", "neutral")
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

        self.install_btn = QtWidgets.QPushButton("Baixar")
        self.install_btn.setObjectName("Primary")
        self.install_btn.setMinimumWidth(120)
        self.install_btn.clicked.connect(self.start_install)
        buttons.addWidget(self.install_btn)

        self.cancel_btn = QtWidgets.QPushButton("Cancelar")
        self.cancel_btn.setMinimumWidth(120)
        self.cancel_btn.clicked.connect(self._cancel)
        self.cancel_btn.setVisible(False)
        buttons.addWidget(self.cancel_btn)

        self.remove_btn = QtWidgets.QPushButton("Remover")
        self.remove_btn.setObjectName("Danger")
        self.remove_btn.setMinimumWidth(120)
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
        if self.component.required:
            chips.append(("Obrigatório", "warning"))
        elif self.component.recommended:
            chips.append(("Recomendado", "accent"))
        if self.component.quality:
            chips.append((self.component.quality, "neutral"))
        if self.component.speed:
            chips.append((self.component.speed, "neutral"))
        return chips

    def refresh(self) -> None:
        from jp2subs.runtime.manager import manager

        if self._worker is not None:
            return
        status = manager.status(self.component.key)
        installed = bool(status and status.installed)
        self.status_chip.set_status(
            "Instalado" if installed else "Não instalado", "success" if installed else "neutral"
        )
        if installed and status:
            self.size_label.setText(f"{human_size(status.size)} em disco")
        else:
            self.size_label.setText(f"Download de aproximadamente {human_size(self.component.approx_size)}")
        self.install_btn.setVisible(not installed)
        self.remove_btn.setVisible(installed)
        self.cancel_btn.setVisible(False)
        self.progress.setVisible(False)
        self.detail_label.setVisible(False)

    def set_busy(self, busy: bool) -> None:
        self.install_btn.setVisible(not busy and not self.remove_btn.isVisible())
        self.cancel_btn.setVisible(busy)
        self.progress.setVisible(busy)
        self.detail_label.setVisible(busy)
        if busy:
            self.remove_btn.setVisible(False)
            self.status_chip.set_status("Baixando...", "accent")

    # -- actions ----------------------------------------------------------

    def start_install(self) -> None:
        if self._worker is not None:
            return
        self.set_busy(True)
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.detail_label.setText("Iniciando o download...")

        worker = ComponentInstallWorker(self.component.key, component=self.component)
        worker.signals.progress.connect(self._on_progress)
        worker.signals.detail.connect(self._on_detail)
        worker.signals.finished.connect(self._on_finished)
        worker.signals.cancelled.connect(self._on_cancelled)
        worker.signals.failed.connect(self._on_failed)
        self._worker = worker
        QtCore.QThreadPool.globalInstance().start(worker)

    def _cancel(self) -> None:
        if self._worker:
            self._worker.cancel()
            self.detail_label.setText("Cancelando...")

    def _remove(self) -> None:
        from jp2subs.runtime.manager import manager

        confirm = QtWidgets.QMessageBox.question(
            self,
            "Remover componente",
            f"Apagar {self.component.name} do disco?",
            QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No,
            QtWidgets.QMessageBox.No,
        )
        if confirm != QtWidgets.QMessageBox.Yes:
            return
        try:
            manager.uninstall(self.component.key)
        except Exception as exc:  # noqa: BLE001
            QtWidgets.QMessageBox.warning(self, "Não deu para remover", str(exc))
            return
        self.refresh()
        self.changed.emit()

    # -- worker signals ---------------------------------------------------

    def _on_progress(self, _key: str, percent: int) -> None:
        if percent < 0:
            self.progress.setRange(0, 0)  # busy indicator: size still unknown
        else:
            self.progress.setRange(0, 100)
            self.progress.setValue(percent)

    def _on_detail(self, _key: str, detail: str) -> None:
        self.detail_label.setText(detail)

    def _finish(self) -> None:
        self._worker = None
        self.refresh()
        self.changed.emit()

    def _on_finished(self, _key: str) -> None:
        self._finish()

    def _on_cancelled(self, _key: str) -> None:
        self._finish()

    def _on_failed(self, _key: str, message: str) -> None:
        self._finish()
        QtWidgets.QMessageBox.warning(
            self, "O download falhou", f"{self.component.name}\n\n{message}"
        )


def open_folder(path: Path | str) -> None:
    """Open a file's folder in the system file manager."""

    target = Path(path)
    if target.is_file():
        target = target.parent
    if target.exists():
        QtGui.QDesktopServices.openUrl(QtCore.QUrl.fromLocalFile(str(target)))


def open_file(path: Path | str) -> None:
    target = Path(path)
    if target.exists():
        QtGui.QDesktopServices.openUrl(QtCore.QUrl.fromLocalFile(str(target)))


def card(title: str, hint: str = "", icon_name: str = "") -> Card:
    return Card(title, hint, icon_name=icon_name)


def icon_button(text: str, icon_name: str, *, primary: bool = False) -> IconButton:
    return IconButton(text, icon_name, primary=primary)
