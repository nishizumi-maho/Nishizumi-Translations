"""Picking where models, FFmpeg and GPU libraries are installed.

The same flow is offered from the first-run dialog, the Components page and
Settings, so it lives here once: choose a folder, sanity-check it, optionally
carry the existing downloads across, and report what happened.
"""
from __future__ import annotations

from pathlib import Path

from PySide6 import QtCore, QtWidgets

from ..runtime import store
from ..runtime.manager import manager
from .workers import RelocateWorker


def location_summary() -> str:
    """One line describing where components live and how much room is left."""

    used = manager.total_size()
    free = store.human_size(store.free_space())
    where = store.data_dir()
    if used:
        return f"{store.human_size(used)} of components in {where} · {free} free"
    return f"Components will be installed in {where} · {free} free"


def change_location(parent: QtWidgets.QWidget) -> bool:
    """Ask for a new folder and switch to it. True when the location changed."""

    forced = store.env_override()
    if forced:
        QtWidgets.QMessageBox.information(
            parent,
            "Location is set by the environment",
            f"{store.ENV_DATA_DIR} points at\n{forced}\n\n"
            "Clear that variable to choose a folder here.",
        )
        return False

    current = store.data_dir()
    chosen = QtWidgets.QFileDialog.getExistingDirectory(
        parent,
        "Choose where models and tools are installed",
        str(current if current.exists() else current.parent),
    )
    if not chosen:
        return False

    target = _tidy_target(parent, Path(chosen))
    if target is None:
        return False
    if target == current:
        QtWidgets.QMessageBox.information(
            parent, "Already there", f"Components are already installed in\n{target}"
        )
        return False

    problem = store.validate_location(target)
    if problem:
        QtWidgets.QMessageBox.warning(parent, "Cannot use that folder", problem)
        return False

    move_existing = _ask_about_existing(parent, current, target)
    if move_existing is None:
        return False

    return _run_relocation(parent, target, move_existing)


def reset_location(parent: QtWidgets.QWidget) -> bool:
    """Go back to the standard per-user folder."""

    default = store.default_data_dir()
    if store.data_dir() == default:
        return False
    answer = QtWidgets.QMessageBox.question(
        parent,
        "Use the default folder?",
        f"Components will go back to\n{default}",
        QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No,
        QtWidgets.QMessageBox.Yes,
    )
    if answer != QtWidgets.QMessageBox.Yes:
        return False

    move_existing = _ask_about_existing(parent, store.data_dir(), default)
    if move_existing is None:
        return False
    return _run_relocation(parent, None, move_existing)


# -- steps -----------------------------------------------------------------


def _tidy_target(parent: QtWidgets.QWidget, chosen: Path) -> Path | None:
    """Offer a subfolder when the user picked a drive root or a busy folder."""

    if store.looks_like_data_dir(chosen):
        return chosen

    suggestion = chosen / "jp2subs"
    answer = QtWidgets.QMessageBox.question(
        parent,
        "Use a subfolder?",
        f"{chosen} already holds other files.\n\n"
        f"Install the components into\n{suggestion}\ninstead, so removing them "
        "never touches anything else?",
        QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.Cancel,
        QtWidgets.QMessageBox.Yes,
    )
    return suggestion if answer == QtWidgets.QMessageBox.Yes else None


def _ask_about_existing(parent: QtWidgets.QWidget, current: Path, target: Path) -> bool | None:
    """True to move what is installed, False to leave it, None to cancel."""

    used = store.dir_size(current)
    if not used:
        return False

    free = store.free_space(target)
    box = QtWidgets.QMessageBox(parent)
    box.setIcon(QtWidgets.QMessageBox.Question)
    box.setWindowTitle("Move what is already installed?")
    box.setText(
        f"{store.human_size(used)} of models and tools are in\n{current}\n\n"
        f"Moving them keeps everything working right away."
    )
    box.setInformativeText(
        f"{store.human_size(free)} is free on the new drive."
        if free
        else "The new folder is ready."
    )
    move_btn = box.addButton("Move them", QtWidgets.QMessageBox.AcceptRole)
    leave_btn = box.addButton("Start fresh", QtWidgets.QMessageBox.DestructiveRole)
    box.addButton(QtWidgets.QMessageBox.Cancel)
    box.setDefaultButton(move_btn)
    box.exec()

    clicked = box.clickedButton()
    if clicked is move_btn:
        if free and used and free < used * 1.05:
            QtWidgets.QMessageBox.warning(
                parent,
                "Not enough disk space",
                f"Moving needs about {store.human_size(used)} but only "
                f"{store.human_size(free)} is free on that drive.",
            )
            return None
        return True
    if clicked is leave_btn:
        QtWidgets.QMessageBox.information(
            parent,
            "Leaving the old folder alone",
            f"The files stay in\n{current}\n\nDelete them yourself once you are sure "
            "you no longer need them.",
        )
        return False
    return None


def _run_relocation(parent: QtWidgets.QWidget, target: Path | None, move_existing: bool) -> bool:
    """Relocate on a worker thread while a modal progress dialog is up."""

    dialog = QtWidgets.QProgressDialog("Preparing...", "", 0, 100, parent)
    dialog.setWindowTitle("Moving components" if move_existing else "Changing location")
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
        dialog.setLabelText(detail or "Moving files...")

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
        QtWidgets.QMessageBox.critical(
            parent, "Could not change the location", outcome["error"]
        )
        return False

    QtWidgets.QMessageBox.information(
        parent,
        "Location updated",
        f"Models and tools are now installed in\n{outcome.get('location', store.data_dir())}",
    )
    return True
