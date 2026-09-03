"""Choosing which drive the models and FFmpeg live on.

A speech model runs to gigabytes, so the folder has to be movable. The store
itself is shared with the subtitle app: point either of them at a new drive and
both follow.
"""
from __future__ import annotations

from pathlib import Path

from jp2subs.runtime import store
from jp2subs.runtime.manager import manager
from PySide6 import QtCore, QtWidgets

from .. import portable
from ..components import human_size
from .workers import RelocateWorker


def change_location(parent: QtWidgets.QWidget) -> bool:
    """Ask for a new folder and switch to it. True when the folder changed."""

    if portable.is_active():
        QtWidgets.QMessageBox.information(
            parent,
            "Modo portátil",
            f"Neste modo tudo fica junto do programa, em\n{portable.data_dir()}\n\n"
            "Para levar os modelos para outro lugar, mova a pasta inteira do "
            f"programa. Para escolher uma pasta separada, apague o arquivo "
            f"{portable.MARKER_NAME} que fica ao lado do executável.",
        )
        return False

    forced = store.env_override()
    if forced:
        QtWidgets.QMessageBox.information(
            parent,
            "A pasta está definida pelo sistema",
            f"A variável {store.ENV_DATA_DIR} aponta para\n{forced}\n\n"
            "Remova essa variável para poder escolher a pasta aqui.",
        )
        return False

    current = store.data_dir()
    chosen = QtWidgets.QFileDialog.getExistingDirectory(
        parent,
        "Escolher onde guardar os modelos e o FFmpeg",
        str(current if current.exists() else current.parent),
    )
    if not chosen:
        return False

    target = _tidy_target(parent, Path(chosen))
    if target is None:
        return False
    if target == current:
        QtWidgets.QMessageBox.information(
            parent, "Já é essa pasta", f"Os componentes já estão em\n{target}"
        )
        return False

    problem = store.validate_location(target)
    if problem:
        QtWidgets.QMessageBox.warning(parent, "Não dá para usar essa pasta", problem)
        return False

    move_existing = _ask_about_existing(parent, current, target)
    if move_existing is None:
        return False
    return _run_relocation(parent, target, move_existing)


def _tidy_target(parent: QtWidgets.QWidget, chosen: Path) -> Path | None:
    """Offer a subfolder when the user picked a drive root or a busy folder."""

    if store.looks_like_data_dir(chosen):
        return chosen

    suggestion = chosen / "jp2subs"
    answer = QtWidgets.QMessageBox.question(
        parent,
        "Usar uma subpasta?",
        f"{chosen} já tem outros arquivos.\n\n"
        f"Instalar os componentes em\n{suggestion}\nassim, remover um componente "
        "nunca mexe no resto?",
        QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.Cancel,
        QtWidgets.QMessageBox.Yes,
    )
    return suggestion if answer == QtWidgets.QMessageBox.Yes else None


def _ask_about_existing(parent: QtWidgets.QWidget, current: Path, target: Path) -> bool | None:
    """True to move what is installed, False to leave it, None to give up."""

    used = store.dir_size(current)
    if not used:
        return False

    free = store.free_space(target)
    box = QtWidgets.QMessageBox(parent)
    box.setIcon(QtWidgets.QMessageBox.Question)
    box.setWindowTitle("Levar junto o que já foi baixado?")
    box.setText(
        f"Há {human_size(used)} de modelos e ferramentas em\n{current}\n\n"
        "Levando tudo junto, nada precisa ser baixado de novo."
    )
    box.setInformativeText(
        f"O disco novo tem {human_size(free)} livres." if free else "A pasta nova está pronta."
    )
    move_btn = box.addButton("Levar junto", QtWidgets.QMessageBox.AcceptRole)
    leave_btn = box.addButton("Começar do zero", QtWidgets.QMessageBox.DestructiveRole)
    box.addButton(QtWidgets.QMessageBox.Cancel)
    box.setDefaultButton(move_btn)
    box.exec()

    clicked = box.clickedButton()
    if clicked is move_btn:
        if free and used and free < used * 1.05:
            QtWidgets.QMessageBox.warning(
                parent,
                "Espaço insuficiente",
                f"Mover exige cerca de {human_size(used)}, mas só há "
                f"{human_size(free)} livres nesse disco.",
            )
            return None
        return True
    if clicked is leave_btn:
        QtWidgets.QMessageBox.information(
            parent,
            "A pasta antiga fica como está",
            f"Os arquivos continuam em\n{current}\n\nApague-os você mesmo quando tiver certeza "
            "de que não precisa mais deles.",
        )
        return False
    return None


def _run_relocation(parent: QtWidgets.QWidget, target: Path | None, move_existing: bool) -> bool:
    """Relocate on a worker thread while a modal progress dialog is up."""

    dialog = QtWidgets.QProgressDialog("Preparando...", "", 0, 100, parent)
    dialog.setWindowTitle("Movendo os componentes" if move_existing else "Mudando de pasta")
    dialog.setCancelButton(None)  # a half-moved tree would be worse than waiting
    dialog.setWindowModality(QtCore.Qt.WindowModal)
    dialog.setMinimumDuration(0)
    dialog.setAutoClose(False)
    dialog.setValue(0)

    outcome: dict[str, str] = {}
    loop = QtCore.QEventLoop(parent)

    def on_progress(moved: int, total: int, detail: str) -> None:
        if total > 0:
            dialog.setValue(min(int(moved * 100 / total), 100))
        dialog.setLabelText(detail or "Movendo arquivos...")

    def on_finished(location: str) -> None:
        outcome["location"] = location
        loop.quit()

    def on_failed(message: str) -> None:
        outcome["error"] = message
        loop.quit()

    worker = RelocateWorker(target, move_existing=move_existing)
    worker.signals.progress.connect(on_progress)
    worker.signals.finished.connect(on_finished)
    worker.signals.failed.connect(on_failed)
    QtCore.QThreadPool.globalInstance().start(worker)
    loop.exec()
    dialog.close()

    if "error" in outcome:
        QtWidgets.QMessageBox.critical(parent, "Não deu para mudar de pasta", outcome["error"])
        return False

    manager.refresh()
    QtWidgets.QMessageBox.information(
        parent,
        "Pasta atualizada",
        f"Os modelos e ferramentas agora ficam em\n{outcome.get('location', store.data_dir())}",
    )
    return True
