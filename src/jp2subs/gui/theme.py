"""Design tokens and the global stylesheet for the desktop app.

Two palettes share one stylesheet template, so adding a colour means adding it
to both :data:`DARK` and :data:`LIGHT` and nothing else.
"""
from __future__ import annotations

from dataclasses import dataclass

from PySide6 import QtGui, QtWidgets


@dataclass(frozen=True)
class Palette:
    """Every colour the stylesheet is allowed to reference."""

    name: str
    canvas: str          # window background
    surface: str         # cards
    surface_alt: str     # inputs, nested panels
    surface_hover: str
    sidebar: str
    border: str
    border_strong: str
    text: str
    text_muted: str
    text_faint: str
    accent: str
    accent_hover: str
    accent_pressed: str
    accent_text: str
    accent_soft: str     # tinted background for selected nav / chips
    success: str
    success_soft: str
    warning: str
    warning_soft: str
    danger: str
    danger_soft: str
    shadow: str


DARK = Palette(
    name="dark",
    canvas="#0b0f19",
    surface="#141a29",
    surface_alt="#0f1421",
    surface_hover="#1c2436",
    sidebar="#0e1320",
    border="#232c40",
    border_strong="#33405c",
    text="#e8ecf5",
    text_muted="#98a3bb",
    text_faint="#6b7794",
    accent="#6366f1",
    accent_hover="#7c7ef5",
    accent_pressed="#4f46e5",
    accent_text="#ffffff",
    accent_soft="#232a4d",
    success="#34d399",
    success_soft="#12312a",
    warning="#fbbf24",
    warning_soft="#332708",
    danger="#f87171",
    danger_soft="#3a1a1d",
    shadow="rgba(0, 0, 0, 0.45)",
)

LIGHT = Palette(
    name="light",
    canvas="#f4f6fb",
    surface="#ffffff",
    surface_alt="#f7f9fd",
    surface_hover="#eef1f8",
    sidebar="#ffffff",
    border="#e1e6f0",
    border_strong="#c8d0e0",
    text="#141a29",
    text_muted="#5b6780",
    text_faint="#8a94aa",
    accent="#4f46e5",
    accent_hover="#4338ca",
    accent_pressed="#3730a3",
    accent_text="#ffffff",
    accent_soft="#ecebfd",
    success="#059669",
    success_soft="#e5f6f0",
    warning="#b45309",
    warning_soft="#fdf3e2",
    danger="#dc2626",
    danger_soft="#fdeaea",
    shadow="rgba(15, 23, 42, 0.12)",
)

PALETTES = {"dark": DARK, "light": LIGHT}

#: Current palette, so widgets that paint themselves can match the stylesheet.
_active: Palette = DARK


def active_palette() -> Palette:
    return _active


def palette_for(name: str) -> Palette:
    return PALETTES.get((name or "dark").lower(), DARK)


def _qt_palette(colors: Palette) -> QtGui.QPalette:
    palette = QtGui.QPalette()
    palette.setColor(QtGui.QPalette.Window, QtGui.QColor(colors.canvas))
    palette.setColor(QtGui.QPalette.WindowText, QtGui.QColor(colors.text))
    palette.setColor(QtGui.QPalette.Base, QtGui.QColor(colors.surface_alt))
    palette.setColor(QtGui.QPalette.AlternateBase, QtGui.QColor(colors.surface))
    palette.setColor(QtGui.QPalette.ToolTipBase, QtGui.QColor(colors.surface))
    palette.setColor(QtGui.QPalette.ToolTipText, QtGui.QColor(colors.text))
    palette.setColor(QtGui.QPalette.Text, QtGui.QColor(colors.text))
    palette.setColor(QtGui.QPalette.Button, QtGui.QColor(colors.surface))
    palette.setColor(QtGui.QPalette.ButtonText, QtGui.QColor(colors.text))
    palette.setColor(QtGui.QPalette.BrightText, QtGui.QColor(colors.danger))
    palette.setColor(QtGui.QPalette.Highlight, QtGui.QColor(colors.accent))
    palette.setColor(QtGui.QPalette.HighlightedText, QtGui.QColor(colors.accent_text))
    palette.setColor(QtGui.QPalette.Link, QtGui.QColor(colors.accent))
    palette.setColor(QtGui.QPalette.PlaceholderText, QtGui.QColor(colors.text_faint))

    disabled = QtGui.QColor(colors.text_faint)
    for role in (QtGui.QPalette.Text, QtGui.QPalette.ButtonText, QtGui.QPalette.WindowText):
        palette.setColor(QtGui.QPalette.Disabled, role, disabled)
    return palette


def build_stylesheet(c: Palette) -> str:
    return f"""
QWidget {{
    color: {c.text};
    font-size: 13px;
}}

QWidget#Canvas, QMainWindow {{
    background-color: {c.canvas};
}}

/* ---------- sidebar ---------- */

QFrame#Sidebar {{
    background-color: {c.sidebar};
    border-right: 1px solid {c.border};
}}

QLabel#BrandName {{
    font-size: 15px;
    font-weight: 700;
    color: {c.text};
}}

QLabel#BrandVersion {{
    font-size: 11px;
    color: {c.text_faint};
}}

QPushButton#NavItem {{
    background-color: transparent;
    border: none;
    border-radius: 9px;
    padding: 9px 12px;
    text-align: left;
    font-size: 13px;
    font-weight: 500;
    color: {c.text_muted};
}}

QPushButton#NavItem:hover {{
    background-color: {c.surface_hover};
    color: {c.text};
}}

QPushButton#NavItem:checked {{
    background-color: {c.accent_soft};
    color: {c.accent};
    font-weight: 600;
}}

/* ---------- page chrome ---------- */

QLabel#PageTitle {{
    font-size: 22px;
    font-weight: 700;
    color: {c.text};
}}

QLabel#PageSubtitle {{
    font-size: 13px;
    color: {c.text_muted};
}}

QLabel#CardTitle {{
    font-size: 14px;
    font-weight: 600;
    color: {c.text};
}}

QLabel#CardHint, QLabel#Hint {{
    font-size: 12px;
    color: {c.text_muted};
}}

QLabel#Muted {{
    color: {c.text_muted};
}}

QLabel#Faint {{
    color: {c.text_faint};
    font-size: 12px;
}}

QFrame#Card {{
    background-color: {c.surface};
    border: 1px solid {c.border};
    border-radius: 14px;
}}

QFrame#Inset {{
    background-color: {c.surface_alt};
    border: 1px solid {c.border};
    border-radius: 10px;
}}

QFrame#Divider {{
    background-color: {c.border};
    max-height: 1px;
    border: none;
}}

/* ---------- buttons ---------- */

QPushButton {{
    background-color: {c.surface_alt};
    color: {c.text};
    border: 1px solid {c.border_strong};
    border-radius: 9px;
    padding: 7px 14px;
    font-weight: 500;
}}

QPushButton:hover {{
    background-color: {c.surface_hover};
    border-color: {c.accent};
}}

QPushButton:pressed {{
    background-color: {c.accent_soft};
}}

QPushButton:disabled {{
    color: {c.text_faint};
    border-color: {c.border};
    background-color: {c.surface_alt};
}}

QPushButton#Primary {{
    background-color: {c.accent};
    color: {c.accent_text};
    border: 1px solid {c.accent};
    font-weight: 600;
    padding: 9px 22px;
}}

QPushButton#Primary:hover {{
    background-color: {c.accent_hover};
    border-color: {c.accent_hover};
}}

QPushButton#Primary:pressed {{
    background-color: {c.accent_pressed};
}}

QPushButton#Primary:disabled {{
    background-color: {c.surface_hover};
    border-color: {c.border};
    color: {c.text_faint};
}}

QPushButton#Danger {{
    color: {c.danger};
    border-color: {c.border_strong};
}}

QPushButton#Danger:hover {{
    background-color: {c.danger_soft};
    border-color: {c.danger};
}}

QPushButton#Ghost {{
    background-color: transparent;
    border: none;
    color: {c.accent};
    padding: 4px 8px;
    font-weight: 600;
}}

QPushButton#Ghost:hover {{
    color: {c.accent_hover};
    background-color: {c.accent_soft};
}}

QPushButton#Link {{
    background: transparent;
    border: none;
    color: {c.accent};
    padding: 0;
    text-align: left;
    font-weight: 500;
}}

QToolButton#Disclosure {{
    background: transparent;
    border: none;
    color: {c.text_muted};
    font-weight: 600;
    padding: 2px;
}}

QToolButton#Disclosure:hover {{
    color: {c.text};
}}

/* ---------- inputs ---------- */

QLineEdit, QPlainTextEdit, QTextEdit, QSpinBox, QDoubleSpinBox, QComboBox {{
    background-color: {c.surface_alt};
    color: {c.text};
    border: 1px solid {c.border_strong};
    border-radius: 9px;
    padding: 6px 10px;
    selection-background-color: {c.accent};
    selection-color: {c.accent_text};
}}

QLineEdit:focus, QPlainTextEdit:focus, QTextEdit:focus,
QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus {{
    border-color: {c.accent};
}}

QLineEdit:disabled, QComboBox:disabled, QSpinBox:disabled {{
    color: {c.text_faint};
}}

/* The drop-down and spin-box arrows are left to the Fusion style. Overriding
   those subcontrols in a stylesheet suppresses the native arrow, and Qt does
   not honour the CSS border-triangle trick used on the web. */

QComboBox QAbstractItemView {{
    background-color: {c.surface};
    border: 1px solid {c.border_strong};
    border-radius: 8px;
    padding: 4px;
    selection-background-color: {c.accent_soft};
    selection-color: {c.text};
    outline: none;
}}

QCheckBox {{
    spacing: 8px;
    color: {c.text};
}}

QCheckBox::indicator {{
    width: 17px;
    height: 17px;
    border-radius: 5px;
    border: 1px solid {c.border_strong};
    background-color: {c.surface_alt};
}}

QCheckBox::indicator:hover {{
    border-color: {c.accent};
}}

QCheckBox::indicator:checked {{
    background-color: {c.accent};
    border-color: {c.accent};
    image: none;
}}

/* ---------- lists ---------- */

QListWidget, QTreeWidget {{
    background-color: {c.surface_alt};
    border: 1px solid {c.border};
    border-radius: 10px;
    padding: 4px;
    outline: none;
}}

QListWidget::item {{
    padding: 7px 8px;
    border-radius: 7px;
    color: {c.text};
}}

QListWidget::item:selected {{
    background-color: {c.accent_soft};
    color: {c.text};
}}

QListWidget::item:hover {{
    background-color: {c.surface_hover};
}}

QListWidget#DropList {{
    min-height: 132px;
}}

QTextEdit#LogView {{
    background-color: {c.surface_alt};
    font-family: "Cascadia Mono", "JetBrains Mono", "Consolas", monospace;
    font-size: 11px;
    color: {c.text_muted};
    min-height: 150px;
}}

/* ---------- progress ---------- */

QProgressBar {{
    background-color: {c.surface_alt};
    border: none;
    border-radius: 6px;
    height: 8px;
    text-align: center;
    color: transparent;
}}

QProgressBar::chunk {{
    background-color: {c.accent};
    border-radius: 6px;
}}

QProgressBar#Slim {{
    height: 6px;
}}

/* ---------- misc ---------- */

QScrollArea {{
    background: transparent;
    border: none;
}}

QScrollArea > QWidget > QWidget {{
    background: transparent;
}}

QScrollBar:vertical {{
    background: transparent;
    width: 10px;
    margin: 2px;
}}

QScrollBar::handle:vertical {{
    background: {c.border_strong};
    border-radius: 5px;
    min-height: 30px;
}}

QScrollBar::handle:vertical:hover {{
    background: {c.text_faint};
}}

QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical,
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{
    background: none;
    height: 0;
}}

QScrollBar:horizontal {{
    background: transparent;
    height: 10px;
    margin: 2px;
}}

QScrollBar::handle:horizontal {{
    background: {c.border_strong};
    border-radius: 5px;
    min-width: 30px;
}}

QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal,
QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {{
    background: none;
    width: 0;
}}

QToolTip {{
    background-color: {c.surface};
    color: {c.text};
    border: 1px solid {c.border_strong};
    border-radius: 6px;
    padding: 5px 8px;
}}

QStatusBar {{
    background-color: {c.sidebar};
    border-top: 1px solid {c.border};
    color: {c.text_muted};
}}

QStatusBar::item {{
    border: none;
}}

QMessageBox, QDialog {{
    background-color: {c.canvas};
}}

QGroupBox {{
    border: 1px solid {c.border};
    border-radius: 10px;
    margin-top: 10px;
    padding-top: 8px;
    color: {c.text_muted};
}}

QGroupBox::title {{
    subcontrol-origin: margin;
    left: 12px;
    padding: 0 5px;
    font-weight: 600;
}}
"""


def apply_app_theme(app: QtWidgets.QApplication, theme: str = "dark") -> Palette:
    """Apply a palette to the whole application and return it."""

    global _active
    colors = palette_for(theme)
    _active = colors

    app.setStyle("Fusion")
    app.setPalette(_qt_palette(colors))

    font = app.font()
    for family in ("Segoe UI Variable Text", "Segoe UI", "Inter", "Noto Sans"):
        if family in QtGui.QFontDatabase.families():
            font.setFamily(family)
            break
    font.setPointSize(10)
    app.setFont(font)

    app.setStyleSheet(build_stylesheet(colors))
    return colors
