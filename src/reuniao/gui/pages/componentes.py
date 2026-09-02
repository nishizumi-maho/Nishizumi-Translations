"""Components page: everything the app downloads for itself, in one list."""
from __future__ import annotations

from jp2subs.gui.common import Banner, Card, ScrollPage, label
from jp2subs.runtime import store
from PySide6 import QtCore, QtWidgets

from ... import components
from ..storage import change_location
from ..widgets import ComponentRow, open_folder


class ComponentsPage(ScrollPage):
    """One row per downloadable item, plus where it all lands on disk."""

    #: Emitted whenever something was installed or removed.
    components_changed = QtCore.Signal()

    def __init__(self, parent: QtWidgets.QWidget | None = None):
        super().__init__(
            "Componentes",
            "Tudo que o aplicativo precisa é baixado por aqui. Nada de instalar à mão.",
            parent,
        )
        self._rows: list[ComponentRow] = []

        self._build_status_card()
        for title, hint, items in components.page_sections():
            self._add_section(title, hint, items)
        self.content.addStretch(1)
        self.refresh()

    # -- construction -----------------------------------------------------

    def _build_status_card(self) -> None:
        card = Card("Onde tudo é guardado", "", icon_name="download")

        self.location_label = label("", "CardHint")
        card.body.addWidget(self.location_label)

        self.summary_label = label("", "Faint")
        card.body.addWidget(self.summary_label)

        row = QtWidgets.QHBoxLayout()
        row.setSpacing(8)
        change = QtWidgets.QPushButton("Mudar de pasta")
        change.clicked.connect(self._change_location)
        row.addWidget(change)
        reveal = QtWidgets.QPushButton("Abrir a pasta")
        reveal.clicked.connect(lambda: open_folder(store.data_dir()))
        row.addWidget(reveal)
        row.addStretch(1)
        card.body.addLayout(row)

        self.banner = Banner("", "warning")
        self.banner.setVisible(False)
        card.body.addWidget(self.banner)

        self.content.addWidget(card)

    def _add_section(self, title: str, hint: str, items) -> None:
        card = Card(title, hint)
        for item in items:
            row = ComponentRow(item)
            row.changed.connect(self._on_row_changed)
            self._rows.append(row)
            card.body.addWidget(row)
        self.content.addWidget(card)

    # -- state ------------------------------------------------------------

    def refresh(self) -> None:
        for row in self._rows:
            row.refresh()
        self._update_summary()

    def _update_summary(self) -> None:
        self.location_label.setText(str(store.data_dir()))
        installed = components.installed_size()
        free = store.free_space()
        self.summary_label.setText(
            f"{components.human_size(installed)} instalados · "
            f"{components.human_size(free)} livres nesse disco"
        )
        missing = components.missing_essentials()
        if missing:
            names = ", ".join(item.name for item in missing)
            self.banner.set_message(f"Ainda falta baixar: {names}.", "warning")
            self.banner.setVisible(True)
        else:
            self.banner.setVisible(False)

    def _on_row_changed(self) -> None:
        self._update_summary()
        self.components_changed.emit()

    def _change_location(self) -> None:
        if change_location(self):
            self.refresh()
            self.components_changed.emit()
