"""About page: what this build is, and where it came from."""
from __future__ import annotations

from jp2subs.gui import icons
from jp2subs.gui.common import Banner, Card, ScrollPage, label
from PySide6 import QtCore, QtWidgets

from ... import branding, diarize


class AboutPage(ScrollPage):
    """Version, the experimental warning, and links."""

    def __init__(self, parent: QtWidgets.QWidget | None = None):
        super().__init__("Sobre", branding.APP_TAGLINE, parent)

        self._build_identity_card()
        self._build_state_card()
        self._build_links_card()
        self.content.addStretch(1)
        self.refresh_components()

    def _build_identity_card(self) -> None:
        card = Card()
        row = QtWidgets.QHBoxLayout()
        row.setSpacing(16)

        self._logo = QtWidgets.QLabel()
        self._logo.setPixmap(icons.app_logo(56))
        self._logo.setFixedSize(56, 56)
        row.addWidget(self._logo, 0, QtCore.Qt.AlignTop)

        text = QtWidgets.QVBoxLayout()
        text.setSpacing(4)
        text.addWidget(label(f"{branding.APP_NAME} {branding.VERSION}", "CardTitle"))
        text.addWidget(label(branding.about_text(), "CardHint"))
        row.addLayout(text, 1)

        card.body.addLayout(row)
        card.body.addWidget(Banner(branding.EXPERIMENTAL_NOTICE, "warning"))
        self.content.addWidget(card)

    def _build_state_card(self) -> None:
        card = Card("Estado desta instalação", "", icon_name="cpu")
        self.state_label = label("", "CardHint")
        card.body.addWidget(self.state_label)
        self.content.addWidget(card)

    def _build_links_card(self) -> None:
        card = Card("Links", "", icon_name="external")
        for text, url in (
            ("Código e histórico do projeto", branding.REPO_URL),
            ("Relatar um problema", branding.ISSUES_URL),
            ("Versões publicadas", branding.RELEASES_URL),
        ):
            link = QtWidgets.QLabel(f'<a href="{url}">{text}</a>')
            link.setOpenExternalLinks(True)
            link.setTextInteractionFlags(QtCore.Qt.TextBrowserInteraction)
            card.body.addWidget(link)
        self.content.addWidget(card)

    def refresh_components(self) -> None:
        from ... import components

        models = ", ".join(item.name for item in components.installed_models()) or "nenhum"
        reason = diarize.unavailable_reason()
        speakers = "pronta para usar" if not reason else reason
        self.state_label.setText(
            f"Modelos instalados: {models}\n"
            f"Identificação de interlocutores: {speakers}\n"
            f"Total em disco: {components.human_size(components.installed_size())}"
        )

    def retheme(self) -> None:
        self._logo.setPixmap(icons.app_logo(56))
