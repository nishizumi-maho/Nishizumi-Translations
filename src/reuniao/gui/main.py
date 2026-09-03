"""Launcher for the desktop app."""
from __future__ import annotations

import sys

from jp2subs.gui import icons
from jp2subs.gui.theme import apply_app_theme
from PySide6 import QtGui, QtWidgets

from .. import branding, portable
from ..config import load_settings
from .window import MainWindow


def _configure_application(app: QtWidgets.QApplication) -> None:
    app.setApplicationName(branding.APP_NAME)
    app.setApplicationDisplayName(branding.APP_NAME)
    app.setApplicationVersion(branding.VERSION)
    app.setOrganizationName(branding.PUBLISHER)
    app.setDesktopFileName(branding.APP_ID)

    if sys.platform.startswith("win"):
        try:
            import ctypes

            # Without an explicit AppUserModelID Windows groups the app under
            # the Python launcher and shows the wrong taskbar icon.
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(  # type: ignore[attr-defined]
                f"{branding.PUBLISHER}.{branding.APP_ID}.{branding.VERSION}"
            )
            # The installer waits on this mutex so an update can close a
            # running copy instead of failing on locked files.
            ctypes.windll.kernel32.CreateMutexW(None, False, "NishizumiReunioesSingleInstance")
        except Exception:  # pragma: no cover - cosmetic only
            pass


def build_window() -> MainWindow:
    """Create the window against an already-themed application."""

    window = MainWindow()
    window.setWindowIcon(QtGui.QIcon(icons.app_logo(64)))
    return window


def launch() -> None:
    """Entry point for ``reuniao ui`` and the ``reuniao-gui`` script."""

    # Before anything reads a path: this decides whether the models and the
    # settings live beside the program or in the user profile.
    portable.activate()

    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv)
    _configure_application(app)

    settings = load_settings()
    apply_app_theme(app, settings.theme)

    window = build_window()
    window.theme_button.setText("Tema claro" if settings.theme == "dark" else "Tema escuro")
    window.show()
    window.run_first_run_checks()

    sys.exit(app.exec())
