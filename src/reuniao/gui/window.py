"""The window: a narrow sidebar and three pages."""
from __future__ import annotations

from jp2subs.gui import icons, theme
from jp2subs.gui.common import StatusChip, label, retheme_tree
from PySide6 import QtCore, QtGui, QtWidgets

from .. import branding, components
from ..config import load_settings, save_settings
from .pages.componentes import ComponentsPage
from .pages.revisar import ReviewPage
from .pages.sobre import AboutPage
from .pages.transcrever import TranscribePage

NAV_ITEMS = (
    ("transcrever", "Transcrever", "waveform"),
    ("revisar", "Revisar", "play"),
    ("componentes", "Componentes", "download"),
    ("sobre", "Sobre", "info"),
)


class NavButton(QtWidgets.QPushButton):
    """Sidebar entry whose icon follows both the palette and the checked state."""

    def __init__(self, key: str, text: str, icon_name: str, parent: QtWidgets.QWidget | None = None):
        super().__init__(text, parent)
        self.key = key
        self._icon_name = icon_name
        self.setObjectName("NavItem")
        self.setCheckable(True)
        self.setCursor(QtCore.Qt.PointingHandCursor)
        self.setIconSize(QtCore.QSize(18, 18))
        self.toggled.connect(lambda _checked: self.retheme())
        self.retheme()

    def retheme(self) -> None:
        colors = theme.active_palette()
        color = colors.accent if self.isChecked() else colors.text_muted
        self.setIcon(icons.icon(self._icon_name, 18, color))


class MainWindow(QtWidgets.QMainWindow):
    """Single window the app runs in."""

    def __init__(self) -> None:
        super().__init__()
        self.settings = load_settings()

        self.setWindowTitle(branding.window_title())
        self.setWindowIcon(QtGui.QIcon(icons.app_logo(64)))
        self.resize(1060, 820)
        self.setMinimumSize(900, 620)

        self._nav_buttons: dict[str, NavButton] = {}
        self._build_ui()
        self._wire_pages()
        self._refresh_readiness()

    # -- construction -----------------------------------------------------

    def _build_ui(self) -> None:
        canvas = QtWidgets.QWidget()
        canvas.setObjectName("Canvas")
        layout = QtWidgets.QHBoxLayout(canvas)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self._build_sidebar(), 0)

        self.stack = QtWidgets.QStackedWidget()
        self.transcribe_page = TranscribePage()
        self.review_page = ReviewPage()
        self.components_page = ComponentsPage()
        self.about_page = AboutPage()
        self._pages = {
            "transcrever": self.transcribe_page,
            "revisar": self.review_page,
            "componentes": self.components_page,
            "sobre": self.about_page,
        }
        for page in self._pages.values():
            self.stack.addWidget(page)
        layout.addWidget(self.stack, 1)

        self.setCentralWidget(canvas)
        status = QtWidgets.QStatusBar()
        status.setSizeGripEnabled(True)
        self.setStatusBar(status)
        self.go_to("transcrever")

    def _build_sidebar(self) -> QtWidgets.QFrame:
        sidebar = QtWidgets.QFrame()
        sidebar.setObjectName("Sidebar")
        sidebar.setFixedWidth(226)

        layout = QtWidgets.QVBoxLayout(sidebar)
        layout.setContentsMargins(16, 20, 16, 16)
        layout.setSpacing(6)

        brand = QtWidgets.QHBoxLayout()
        brand.setSpacing(11)
        self._brand_logo = QtWidgets.QLabel()
        self._brand_logo.setPixmap(icons.app_logo(36))
        self._brand_logo.setFixedSize(36, 36)
        brand.addWidget(self._brand_logo, 0)

        brand_text = QtWidgets.QVBoxLayout()
        brand_text.setSpacing(0)
        name = label("Nishizumi", "BrandName")
        name.setWordWrap(False)
        brand_text.addWidget(name)
        version = label(f"Reuniões · {branding.VERSION}", "BrandVersion")
        version.setWordWrap(False)
        brand_text.addWidget(version)
        brand.addLayout(brand_text, 1)
        layout.addLayout(brand)
        layout.addSpacing(8)

        layout.addWidget(StatusChip("Experimental", "warning"))
        layout.addSpacing(10)

        for key, text, icon_name in NAV_ITEMS:
            button = NavButton(key, text, icon_name)
            button.clicked.connect(lambda _checked=False, target=key: self.go_to(target))
            layout.addWidget(button)
            self._nav_buttons[key] = button

        layout.addStretch(1)

        self.readiness_chip = StatusChip("Verificando...", "neutral")
        layout.addWidget(self.readiness_chip)

        self.theme_button = QtWidgets.QPushButton("Tema claro")
        self.theme_button.setObjectName("Ghost")
        self.theme_button.clicked.connect(self._toggle_theme)
        layout.addWidget(self.theme_button)

        return sidebar

    def _wire_pages(self) -> None:
        self.transcribe_page.navigate.connect(self.go_to)
        self.transcribe_page.transcript_ready.connect(self.review_page.load_transcript)
        self.components_page.components_changed.connect(self._on_components_changed)

    # -- navigation -------------------------------------------------------

    def go_to(self, key: str) -> None:
        page = self._pages.get(key)
        if not page:
            return
        if key == "componentes":
            self.components_page.refresh()
        if key == "sobre":
            self.about_page.refresh_components()
        self.stack.setCurrentWidget(page)
        for nav_key, button in self._nav_buttons.items():
            button.setChecked(nav_key == key)

    # -- state ------------------------------------------------------------

    def _on_components_changed(self) -> None:
        self.transcribe_page.refresh_components()
        self.about_page.refresh_components()
        self._refresh_readiness()

    def _refresh_readiness(self) -> None:
        from jp2subs.runtime.manager import manager

        manager.refresh()
        if components.is_ready():
            self.readiness_chip.set_status("Pronto", "success")
            self.statusBar().showMessage("Pronto — arraste a gravação da reunião para começar.")
        else:
            missing = ", ".join(item.name for item in components.missing_essentials())
            self.readiness_chip.set_status("Falta baixar", "warning")
            self.statusBar().showMessage(f"Ainda falta baixar: {missing}")

    def _toggle_theme(self) -> None:
        self.apply_theme("light" if self.settings.theme == "dark" else "dark")

    def apply_theme(self, name: str) -> None:
        """Switch palettes live, then repaint everything that draws itself."""

        app = QtWidgets.QApplication.instance()
        if not app:
            return
        theme.apply_app_theme(app, name)
        self.settings.theme = name
        save_settings(self.settings)
        retheme_tree(self)
        self._brand_logo.setPixmap(icons.app_logo(36))
        self.setWindowIcon(QtGui.QIcon(icons.app_logo(64)))
        self.theme_button.setText("Tema claro" if name == "dark" else "Tema escuro")

    def run_first_run_checks(self) -> None:
        """Land on Componentes when there is nothing installed to work with."""

        if not components.is_ready():
            self.go_to("componentes")
