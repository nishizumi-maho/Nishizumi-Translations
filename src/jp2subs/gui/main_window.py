"""Application shell: sidebar navigation around a stack of pages."""
from __future__ import annotations

from PySide6 import QtCore, QtGui, QtWidgets

from .. import branding
from ..runtime import store
from ..runtime.manager import manager
from . import icons, theme
from .common import StatusChip, label, retheme_tree
from .pages.about import AboutPage
from .pages.components import ComponentsPage
from .pages.finalize import FinalizePage
from .pages.settings import SettingsPage
from .pages.transcribe import TranscribePage
from .setup_dialog import SetupDialog
from .state import load_app_state, persist_app_state

NAV_ITEMS = (
    ("transcribe", "Transcribe", "waveform"),
    ("finalize", "Finalize", "film"),
    ("components", "Components", "download"),
    ("settings", "Settings", "sliders"),
    ("about", "About", "info"),
)


class NavButton(QtWidgets.QPushButton):
    """Sidebar entry whose icon tracks both the palette and the checked state."""

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
    """The single window the app runs in."""

    def __init__(self) -> None:
        super().__init__()
        self.cfg = load_app_state()

        self.setWindowTitle(branding.window_title())
        self.setWindowIcon(QtGui.QIcon(icons.app_logo(64)))
        self.resize(1180, 800)
        self.setMinimumSize(940, 640)

        self._nav_buttons: dict[str, NavButton] = {}
        self._checked_startup_updates = False

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
        self.finalize_page = FinalizePage()
        self.components_page = ComponentsPage()
        self.settings_page = SettingsPage()
        self.about_page = AboutPage()

        self._pages = {
            "transcribe": self.transcribe_page,
            "finalize": self.finalize_page,
            "components": self.components_page,
            "settings": self.settings_page,
            "about": self.about_page,
        }
        for page in self._pages.values():
            self.stack.addWidget(page)

        layout.addWidget(self.stack, 1)
        self.setCentralWidget(canvas)

        status = QtWidgets.QStatusBar()
        status.setSizeGripEnabled(True)
        self.setStatusBar(status)

        self.go_to("transcribe")

    def _build_sidebar(self) -> QtWidgets.QFrame:
        sidebar = QtWidgets.QFrame()
        sidebar.setObjectName("Sidebar")
        sidebar.setFixedWidth(224)

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
        version = label(f"Translations · {branding.VERSION}", "BrandVersion")
        version.setWordWrap(False)
        brand_text.addWidget(version)
        brand.addLayout(brand_text, 1)
        layout.addLayout(brand)
        layout.addSpacing(18)

        for key, text, icon_name in NAV_ITEMS:
            button = NavButton(key, text, icon_name)
            button.clicked.connect(lambda _checked=False, target=key: self.go_to(target))
            layout.addWidget(button)
            self._nav_buttons[key] = button

        layout.addStretch(1)

        self.readiness_chip = StatusChip("Checking...", "neutral")
        layout.addWidget(self.readiness_chip)
        self.storage_label = label("", "Faint")
        layout.addWidget(self.storage_label)

        return sidebar

    def _wire_pages(self) -> None:
        self.transcribe_page.navigate.connect(self.go_to)
        self.finalize_page.navigate.connect(self.go_to)
        self.settings_page.navigate.connect(self.go_to)

        self.components_page.components_changed.connect(self._on_components_changed)
        self.settings_page.theme_changed.connect(self.apply_theme)
        self.settings_page.settings_saved.connect(self._on_settings_saved)
        self.about_page.update_available.connect(self._on_update_available)

    # -- navigation -------------------------------------------------------

    def go_to(self, key: str) -> None:
        page = self._pages.get(key)
        if not page:
            return
        self.stack.setCurrentWidget(page)
        for nav_key, button in self._nav_buttons.items():
            button.setChecked(nav_key == key)

    # -- state ------------------------------------------------------------

    def _on_components_changed(self) -> None:
        self.transcribe_page.refresh_components()
        self.finalize_page.refresh_components()
        self.settings_page.refresh_components()
        self.about_page.refresh_components()
        self._refresh_readiness()

    def _on_settings_saved(self) -> None:
        self.cfg = load_app_state()
        self.transcribe_page.reload_config()

    @QtCore.Slot(object)
    def _on_update_available(self, release: object) -> None:
        """A background check found a newer release; point the user at About."""

        version = getattr(release, "version", "")
        self._nav_buttons["about"].setText(f"About  •")
        self._nav_buttons["about"].setToolTip(f"Version {version} is available")
        self.statusBar().showMessage(
            f"Version {version} is available — open About to install it.", 15000
        )

    def _refresh_readiness(self) -> None:
        manager.refresh()
        if manager.is_ready():
            self.readiness_chip.set_status("Ready", "success")
            self.statusBar().showMessage("Ready — drop a file on the Transcribe page to start.")
        else:
            missing = ", ".join(item.name for item in manager.missing_required())
            self.readiness_chip.set_status("Setup needed", "warning")
            self.statusBar().showMessage(f"Still to install: {missing}")

        total = manager.total_size()
        self.storage_label.setText(
            f"{store.human_size(total)} installed" if total else "No components installed yet"
        )

    def apply_theme(self, name: str) -> None:
        """Switch palettes live, then repaint everything that draws itself."""

        app = QtWidgets.QApplication.instance()
        if not app:
            return
        theme.apply_app_theme(app, name)
        retheme_tree(self)
        self._brand_logo.setPixmap(icons.app_logo(36))
        self.setWindowIcon(QtGui.QIcon(icons.app_logo(64)))

    # -- lifecycle --------------------------------------------------------

    def run_first_run_checks(self) -> None:
        """Offer the setup dialog, then check for updates if the user wants that."""

        if not manager.is_ready() and not self.cfg.app.setup_completed:
            dialog = SetupDialog(self)
            dialog.exec()
            self.cfg = load_app_state()
            self.cfg.app.setup_completed = True
            persist_app_state(self.cfg)
            self._on_components_changed()
            self.components_page.refresh()

        if not manager.is_ready():
            self.go_to("components")

        if self.cfg.app.check_updates_on_start and not self._checked_startup_updates:
            self._checked_startup_updates = True
            QtCore.QTimer.singleShot(1200, lambda: self.about_page.check_for_updates(silent=True))
