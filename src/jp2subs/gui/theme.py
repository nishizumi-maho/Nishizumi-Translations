"""Modern UI theme for jp2subs GUI."""
from __future__ import annotations

from PySide6 import QtCore, QtGui, QtWidgets


PRIMARY_COLOR = "#4f46e5"  # Indigo accent
PRIMARY_COLOR_DARK = "#3730a3"
SURFACE_DARK = "#020617"
SURFACE_MEDIUM = "#0b1120"
SURFACE_LIGHT = "#111827"
BORDER_COLOR = "#1f2937"
TEXT_PRIMARY = "#e5e7eb"
TEXT_SECONDARY = "#9ca3af"
ERROR_COLOR = "#f97373"
SUCCESS_COLOR = "#22c55e"


def _build_palette() -> QtGui.QPalette:
    """Create a dark palette tuned for the app."""
    palette = QtGui.QPalette()

    # Window / base colors
    palette.setColor(QtGui.QPalette.Window, QtGui.QColor(SURFACE_DARK))
    palette.setColor(QtGui.QPalette.WindowText, QtGui.QColor(TEXT_PRIMARY))
    palette.setColor(QtGui.QPalette.Base, QtGui.QColor(SURFACE_MEDIUM))
    palette.setColor(QtGui.QPalette.AlternateBase, QtGui.QColor(SURFACE_LIGHT))
    palette.setColor(QtGui.QPalette.ToolTipBase, QtGui.QColor(SURFACE_LIGHT))
    palette.setColor(QtGui.QPalette.ToolTipText, QtGui.QColor(TEXT_PRIMARY))

    # Text
    palette.setColor(QtGui.QPalette.Text, QtGui.QColor(TEXT_PRIMARY))
    palette.setColor(QtGui.QPalette.Button, QtGui.QColor(SURFACE_LIGHT))
    palette.setColor(QtGui.QPalette.ButtonText, QtGui.QColor(TEXT_PRIMARY))
    palette.setColor(QtGui.QPalette.BrightText, QtCore.Qt.red)

    # Highlights
    palette.setColor(QtGui.QPalette.Highlight, QtGui.QColor(PRIMARY_COLOR))
    palette.setColor(QtGui.QPalette.HighlightedText, QtGui.QColor("#ffffff"))

    # Links
    palette.setColor(QtGui.QPalette.Link, QtGui.QColor(PRIMARY_COLOR))
    palette.setColor(QtGui.QPalette.LinkVisited, QtGui.QColor(PRIMARY_COLOR_DARK))

    # Disabled state
    disabled = QtGui.QColor(TEXT_SECONDARY)
    palette.setColor(QtGui.QPalette.Disabled, QtGui.QPalette.Text, disabled)
    palette.setColor(QtGui.QPalette.Disabled, QtGui.QPalette.ButtonText, disabled)
    palette.setColor(QtGui.QPalette.Disabled, QtGui.QPalette.WindowText, disabled)

    return palette


EXTRA_STYLESHEET = """
QListWidget#SourceList {
    min-height: 140px;
}

QListWidget#ResultsList {
    min-height: 80px;
}

QTextEdit#LogView {
    min-height: 130px;
    font-family: "JetBrains Mono", "Fira Code", monospace;
    font-size: 11px;
}
"""

GLOBAL_STYLESHEET = f"""
QMainWindow {{
    background-color: {SURFACE_DARK};
}}

QWidget#AppShell {{
    background-color: transparent;
}}

QFrame#Card {{
    background-color: {SURFACE_MEDIUM};
    border-radius: 14px;
    border: 1px solid {BORDER_COLOR};
}}

QLabel#TitleLabel {{
    font-size: 22px;
    font-weight: 600;
    color: {TEXT_PRIMARY};
}}

QLabel#SubtitleLabel {{
    font-size: 12px;
    color: {TEXT_SECONDARY};
}}

QTabWidget::pane {{
    border: none;
    border-radius: 12px;
    background-color: {SURFACE_MEDIUM};
    margin-top: 4px;
}}

QTabBar {{
    border: none;
}}

QTabBar::tab {{
    background-color: transparent;
    color: {TEXT_SECONDARY};
    padding: 6px 14px;
    border-radius: 10px;
    margin-right: 4px;
    font-weight: 500;
    border: none;
}}

QTabBar::tab:selected {{
    background-color: {PRIMARY_COLOR};
    color: #ffffff;
}}

QTabBar::tab:hover:!selected {{
    background-color: {SURFACE_LIGHT};
    color: {TEXT_PRIMARY};
}}

QPushButton {{
    background-color: {SURFACE_LIGHT};
    color: {TEXT_PRIMARY};
    border-radius: 8px;
    border: 1px solid {BORDER_COLOR};
    padding: 6px 12px;
}}

QPushButton:hover {{
    background-color: {PRIMARY_COLOR_DARK};
    border-color: {PRIMARY_COLOR};
}}

QPushButton:pressed {{
    background-color: {PRIMARY_COLOR};
}}

QPushButton:disabled {{
    background-color: {SURFACE_MEDIUM};
    color: {TEXT_SECONDARY};
    border-color: {BORDER_COLOR};
}}

QLineEdit, QTextEdit, QPlainTextEdit, QSpinBox, QDoubleSpinBox, QComboBox {{
    background-color: {SURFACE_DARK};
    color: {TEXT_PRIMARY};
    border-radius: 8px;
    border: 1px solid {BORDER_COLOR};
    padding: 4px 8px;
    selection-background-color: {PRIMARY_COLOR};
}}

QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus,
QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus {{
    border-color: {PRIMARY_COLOR};
}}

QListWidget, QTreeWidget, QTableWidget {{
    background-color: {SURFACE_DARK};
    border-radius: 10px;
    border: 1px solid {BORDER_COLOR};
    padding: 4px;
}}

QProgressBar {{
    border: 1px solid {BORDER_COLOR};
    border-radius: 10px;
    text-align: center;
    background-color: {SURFACE_DARK};
    color: {TEXT_SECONDARY};
}}

QProgressBar::chunk {{
    background-color: {PRIMARY_COLOR};
    border-radius: 8px;
}}

QStatusBar {{
    background-color: {SURFACE_LIGHT};
    border-top: 1px solid {BORDER_COLOR};
}}

QGroupBox {{
    border: 1px solid {BORDER_COLOR};
    border-radius: 10px;
    margin-top: 8px;
    background-color: {SURFACE_MEDIUM};
}}

QGroupBox::title {{
    subcontrol-origin: margin;
    left: 10px;
    padding: 0 4px;
    color: {TEXT_SECONDARY};
    font-weight: 500;
}}

QScrollBar:vertical {{
    background: transparent;
    width: 10px;
    margin: 4px 0 4px 0;
}}

QScrollBar::handle:vertical {{
    background: {SURFACE_LIGHT};
    border-radius: 5px;
}}

QScrollBar::handle:vertical:hover {{
    background: {PRIMARY_COLOR_DARK};
}}

QCheckBox, QLabel {{
    color: {TEXT_PRIMARY};
}}

{EXTRA_STYLESHEET}
"""


def apply_app_theme(app: QtWidgets.QApplication) -> None:
    """Apply palette and global stylesheet to the QApplication."""
    app.setStyle("Fusion")
    app.setPalette(_build_palette())
    base_font = app.font()
    base_font.setPointSize(10)
    app.setFont(base_font)
    app.setStyleSheet(GLOBAL_STYLESHEET)
