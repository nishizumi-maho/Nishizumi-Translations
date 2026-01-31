"""GUI launcher for jp2subs."""
from __future__ import annotations

import sys

from PySide6 import QtWidgets

from .theme import apply_app_theme
from .widgets import MainWindow


def launch() -> None:
    """Entry point for `jp2subs-gui`."""
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv)
    apply_app_theme(app)

    win = MainWindow()
    win.show()

    # Optional: initial status message
    if win.statusBar():
        win.statusBar().showMessage("Ready • Drag audio/video files into the Pipeline tab")

    sys.exit(app.exec())
