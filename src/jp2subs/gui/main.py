"""GUI launcher."""
from __future__ import annotations

import sys

from PySide6 import QtGui, QtWidgets

from .. import branding
from ..config import load_config
from . import icons
from .main_window import MainWindow
from .theme import apply_app_theme


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
            # The installer waits on this mutex (AppMutex in jp2subs.iss) so an
            # update can close a running copy instead of failing on locked files.
            ctypes.windll.kernel32.CreateMutexW(None, False, "NishizumiTranslationsSingleInstance")
        except Exception:  # pragma: no cover - cosmetic only
            pass


def build_window() -> MainWindow:
    """Create the main window against an already-themed application."""

    window = MainWindow()
    window.setWindowIcon(QtGui.QIcon(icons.app_logo(64)))
    return window


def launch() -> None:
    """Entry point for `jp2subs ui` and the `jp2subs-gui` script."""

    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv)
    _configure_application(app)

    config = load_config()
    apply_app_theme(app, config.app.theme)

    window = build_window()
    window.show()
    window.run_first_run_checks()

    sys.exit(app.exec())
