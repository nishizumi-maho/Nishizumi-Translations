"""Entry point for jp2subs GUI."""
from __future__ import annotations

import sys


def launch():  # pragma: no cover - UI bootstrap
    try:
        from PySide6 import QtWidgets
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError("PySide6 não está instalado. Instale jp2subs[gui].") from exc

    from .widgets import MainWindow

    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv)
    window = MainWindow()
    window.show()
    app.exec()


if __name__ == "__main__":  # pragma: no cover
    launch()

