"""Reusable building blocks shared by every page."""
from __future__ import annotations

from pathlib import Path
from typing import Iterable

from PySide6 import QtCore, QtGui, QtWidgets

from . import icons, theme


def hline() -> QtWidgets.QFrame:
    line = QtWidgets.QFrame()
    line.setObjectName("Divider")
    line.setFrameShape(QtWidgets.QFrame.HLine)
    line.setFixedHeight(1)
    return line


def label(text: str, role: str = "") -> QtWidgets.QLabel:
    widget = QtWidgets.QLabel(text)
    if role:
        widget.setObjectName(role)
    widget.setWordWrap(True)
    return widget


def retheme_tree(root: QtWidgets.QWidget) -> None:
    """Re-render anything that painted itself with the previous palette.

    The stylesheet handles most of the app, but widgets that rasterise icons or
    build inline styles need a nudge after the palette changes.
    """

    for widget in [root, *root.findChildren(QtWidgets.QWidget)]:
        hook = getattr(widget, "retheme", None)
        if callable(hook):
            hook()


class IconButton(QtWidgets.QPushButton):
    """Push button whose icon follows the active palette."""

    def __init__(
        self,
        text: str,
        icon_name: str,
        *,
        role: str = "text_muted",
        primary: bool = False,
        parent: QtWidgets.QWidget | None = None,
    ):
        super().__init__(text, parent)
        self._icon_name = icon_name
        self._role = role
        if primary:
            self.setObjectName("Primary")
        self.retheme()

    def retheme(self) -> None:
        color = "#ffffff" if self.objectName() == "Primary" else getattr(
            theme.active_palette(), self._role, theme.active_palette().text_muted
        )
        self.setIcon(icons.icon(self._icon_name, 15, color))


class Card(QtWidgets.QFrame):
    """A titled panel. ``body`` is the layout callers add their content to."""

    def __init__(
        self,
        title: str = "",
        hint: str = "",
        *,
        icon_name: str = "",
        parent: QtWidgets.QWidget | None = None,
    ):
        super().__init__(parent)
        self.setObjectName("Card")

        outer = QtWidgets.QVBoxLayout(self)
        outer.setContentsMargins(18, 16, 18, 18)
        outer.setSpacing(12)

        self.header = QtWidgets.QHBoxLayout()
        self.header.setSpacing(10)

        self._icon_name = icon_name
        self._mark: QtWidgets.QLabel | None = None

        if title:
            if icon_name:
                mark = QtWidgets.QLabel()
                mark.setPixmap(icons.pixmap(icon_name, 18, theme.active_palette().accent))
                mark.setFixedWidth(20)
                self._mark = mark
                self.header.addWidget(mark, 0, QtCore.Qt.AlignTop)

            titles = QtWidgets.QVBoxLayout()
            titles.setSpacing(2)
            titles.addWidget(label(title, "CardTitle"))
            if hint:
                titles.addWidget(label(hint, "CardHint"))
            self.header.addLayout(titles, 1)
            outer.addLayout(self.header)

        self.body = QtWidgets.QVBoxLayout()
        self.body.setSpacing(10)
        outer.addLayout(self.body)

    def add_header_widget(self, widget: QtWidgets.QWidget) -> None:
        self.header.addWidget(widget, 0, QtCore.Qt.AlignTop)

    def retheme(self) -> None:
        if self._mark and self._icon_name:
            self._mark.setPixmap(icons.pixmap(self._icon_name, 18, theme.active_palette().accent))


class StatusChip(QtWidgets.QLabel):
    """Small coloured pill: installed / missing / recommended and friends."""

    TONES = ("neutral", "accent", "success", "warning", "danger")

    def __init__(self, text: str = "", tone: str = "neutral", parent: QtWidgets.QWidget | None = None):
        super().__init__(text, parent)
        self.setAlignment(QtCore.Qt.AlignCenter)
        self._tone = tone
        self.set_tone(tone)

    def set_tone(self, tone: str) -> None:
        self._tone = tone if tone in self.TONES else "neutral"
        colors = theme.active_palette()
        mapping = {
            "neutral": (colors.surface_alt, colors.text_muted, colors.border_strong),
            "accent": (colors.accent_soft, colors.accent, colors.accent),
            "success": (colors.success_soft, colors.success, colors.success),
            "warning": (colors.warning_soft, colors.warning, colors.warning),
            "danger": (colors.danger_soft, colors.danger, colors.danger),
        }
        background, foreground, border = mapping[self._tone]
        self.setStyleSheet(
            f"background-color: {background}; color: {foreground};"
            f" border: 1px solid {border}; border-radius: 9px;"
            " padding: 2px 9px; font-size: 11px; font-weight: 600;"
        )

    def set_status(self, text: str, tone: str) -> None:
        self.setText(text)
        self.set_tone(tone)

    def retheme(self) -> None:
        self.set_tone(self._tone)


class Banner(QtWidgets.QFrame):
    """Inline notice with an optional action button."""

    action_clicked = QtCore.Signal()

    def __init__(
        self,
        text: str = "",
        tone: str = "warning",
        action_text: str = "",
        parent: QtWidgets.QWidget | None = None,
    ):
        super().__init__(parent)
        self.setObjectName("Banner")
        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(14, 11, 14, 11)
        layout.setSpacing(11)

        self._icon = QtWidgets.QLabel()
        layout.addWidget(self._icon, 0, QtCore.Qt.AlignTop)

        self._label = label(text)
        layout.addWidget(self._label, 1)

        self._button = QtWidgets.QPushButton(action_text)
        self._button.setObjectName("Ghost")
        self._button.clicked.connect(self.action_clicked)
        self._button.setVisible(bool(action_text))
        layout.addWidget(self._button, 0, QtCore.Qt.AlignVCenter)

        self._tone = tone
        self.set_tone(tone)

    def set_tone(self, tone: str) -> None:
        self._tone = tone
        colors = theme.active_palette()
        mapping = {
            "accent": (colors.accent_soft, colors.accent, "info"),
            "success": (colors.success_soft, colors.success, "check"),
            "warning": (colors.warning_soft, colors.warning, "alert"),
            "danger": (colors.danger_soft, colors.danger, "alert"),
        }
        background, accent, icon_name = mapping.get(tone, mapping["warning"])
        self.setStyleSheet(
            f"QFrame#Banner {{ background-color: {background}; border: 1px solid {accent};"
            " border-radius: 11px; }"
        )
        self._label.setStyleSheet(f"color: {colors.text}; background: transparent; border: none;")
        self._button.setStyleSheet(
            f"QPushButton {{ color: {accent}; background: transparent; border: none;"
            " font-weight: 700; padding: 4px 6px; }"
        )
        self._icon.setPixmap(icons.pixmap(icon_name, 18, accent))

    def set_message(self, text: str, tone: str = "", action_text: str | None = None) -> None:
        self._label.setText(text)
        if tone:
            self.set_tone(tone)
        if action_text is not None:
            self._button.setText(action_text)
            self._button.setVisible(bool(action_text))

    def retheme(self) -> None:
        self.set_tone(self._tone)


class Collapsible(QtWidgets.QWidget):
    """Disclosure section used to keep advanced options out of the way."""

    def __init__(self, title: str, *, expanded: bool = False, parent: QtWidgets.QWidget | None = None):
        super().__init__(parent)
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        self._toggle = QtWidgets.QToolButton()
        self._toggle.setObjectName("Disclosure")
        self._toggle.setText(title)
        self._toggle.setCheckable(True)
        self._toggle.setChecked(expanded)
        self._toggle.setToolButtonStyle(QtCore.Qt.ToolButtonTextBesideIcon)
        self._toggle.setArrowType(QtCore.Qt.DownArrow if expanded else QtCore.Qt.RightArrow)
        self._toggle.setCursor(QtCore.Qt.PointingHandCursor)
        self._toggle.toggled.connect(self._on_toggled)
        layout.addWidget(self._toggle, 0, QtCore.Qt.AlignLeft)

        self._content = QtWidgets.QWidget()
        self.body = QtWidgets.QVBoxLayout(self._content)
        self.body.setContentsMargins(2, 0, 0, 0)
        self.body.setSpacing(10)
        self._content.setVisible(expanded)
        layout.addWidget(self._content)

    def _on_toggled(self, checked: bool) -> None:
        self._content.setVisible(checked)
        self._toggle.setArrowType(QtCore.Qt.DownArrow if checked else QtCore.Qt.RightArrow)

    def set_expanded(self, expanded: bool) -> None:
        self._toggle.setChecked(expanded)


class DropZone(QtWidgets.QFrame):
    """Dashed target that accepts dropped media files."""

    files_dropped = QtCore.Signal(list)
    browse_requested = QtCore.Signal()

    def __init__(self, parent: QtWidgets.QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("DropZone")
        self.setAcceptDrops(True)
        self.setCursor(QtCore.Qt.PointingHandCursor)
        self.setMinimumHeight(128)
        self._hover = False

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(6)
        layout.setAlignment(QtCore.Qt.AlignCenter)

        self._icon = QtWidgets.QLabel()
        self._icon.setAlignment(QtCore.Qt.AlignCenter)
        layout.addWidget(self._icon)

        self._title = label("Drop audio or video here", "CardTitle")
        self._title.setAlignment(QtCore.Qt.AlignCenter)
        layout.addWidget(self._title)

        self._hint = label("mp4 · mkv · webm · mov · avi · flac · mp3 · wav · m4a · mka", "Faint")
        self._hint.setAlignment(QtCore.Qt.AlignCenter)
        layout.addWidget(self._hint)

        browse = QtWidgets.QPushButton("Choose files")
        browse.clicked.connect(self.browse_requested)
        row = QtWidgets.QHBoxLayout()
        row.addStretch(1)
        row.addWidget(browse)
        row.addStretch(1)
        layout.addLayout(row)

        self._restyle()

    def _restyle(self) -> None:
        colors = theme.active_palette()
        border = colors.accent if self._hover else colors.border_strong
        background = colors.accent_soft if self._hover else colors.surface_alt
        # QLabel derives from QFrame, so the selector has to name this widget or
        # every child label picks up the dashed border too.
        self.setStyleSheet(
            f"QFrame#DropZone {{ border: 2px dashed {border}; border-radius: 13px;"
            f" background-color: {background}; }}"
        )
        self._icon.setPixmap(icons.pixmap("download", 30, colors.accent if self._hover else colors.text_faint))

    def dragEnterEvent(self, event: QtGui.QDragEnterEvent) -> None:  # noqa: N802
        if event.mimeData().hasUrls():
            self._hover = True
            self._restyle()
            event.acceptProposedAction()

    def dragLeaveEvent(self, event: QtCore.QEvent) -> None:  # noqa: N802
        self._hover = False
        self._restyle()
        super().dragLeaveEvent(event)

    def dropEvent(self, event: QtGui.QDropEvent) -> None:  # noqa: N802
        self._hover = False
        self._restyle()
        paths = [url.toLocalFile() for url in event.mimeData().urls() if url.isLocalFile()]
        if paths:
            self.files_dropped.emit(paths)
            event.acceptProposedAction()

    def mousePressEvent(self, event: QtGui.QMouseEvent) -> None:  # noqa: N802
        if event.button() == QtCore.Qt.LeftButton:
            self.browse_requested.emit()
        super().mousePressEvent(event)

    def retheme(self) -> None:
        self._restyle()


class FileQueue(QtWidgets.QListWidget):
    """Queue of source files that also accepts drops of its own."""

    files_dropped = QtCore.Signal(list)

    def __init__(self, parent: QtWidgets.QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("DropList")
        self.setAcceptDrops(True)
        self.setDragDropMode(QtWidgets.QAbstractItemView.DropOnly)
        self.setSelectionMode(QtWidgets.QAbstractItemView.ExtendedSelection)
        self.setUniformItemSizes(True)

    def dragEnterEvent(self, event: QtGui.QDragEnterEvent) -> None:  # noqa: N802
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            super().dragEnterEvent(event)

    def dragMoveEvent(self, event: QtGui.QDragMoveEvent) -> None:  # noqa: N802
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            super().dragMoveEvent(event)

    def dropEvent(self, event: QtGui.QDropEvent) -> None:  # noqa: N802
        paths = [url.toLocalFile() for url in event.mimeData().urls() if url.isLocalFile()]
        if paths:
            self.files_dropped.emit(paths)
            event.acceptProposedAction()
        else:
            super().dropEvent(event)

    def paths(self) -> list[Path]:
        return [Path(self.item(index).data(QtCore.Qt.UserRole)) for index in range(self.count())]

    def contains(self, path: str) -> bool:
        return any(self.item(index).data(QtCore.Qt.UserRole) == path for index in range(self.count()))

    def add_path(self, path: str) -> bool:
        if self.contains(path):
            return False
        source = Path(path)
        item = QtWidgets.QListWidgetItem(source.name)
        item.setData(QtCore.Qt.UserRole, path)
        try:
            size = source.stat().st_size
            item.setToolTip(f"{path}\n{_pretty_size(size)}")
        except OSError:
            item.setToolTip(path)
        item.setIcon(icons.icon("film", 16, theme.active_palette().text_muted))
        self.addItem(item)
        return True


class StageTimeline(QtWidgets.QWidget):
    """Vertical list of pipeline stages with pending/active/done states."""

    def __init__(self, stages: Iterable[str], parent: QtWidgets.QWidget | None = None):
        super().__init__(parent)
        self._rows: dict[str, tuple[QtWidgets.QLabel, QtWidgets.QLabel]] = {}

        self._states: dict[str, str] = {}
        self._holders: dict[str, QtWidgets.QWidget] = {}

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(9)

        for stage in stages:
            holder = QtWidgets.QWidget()
            row = QtWidgets.QHBoxLayout(holder)
            row.setContentsMargins(0, 0, 0, 0)
            row.setSpacing(9)
            marker = QtWidgets.QLabel()
            marker.setFixedSize(18, 18)
            text = QtWidgets.QLabel(stage)
            row.addWidget(marker, 0)
            row.addWidget(text, 1)
            layout.addWidget(holder)
            self._rows[stage] = (marker, text)
            self._holders[stage] = holder

        self.reset()

    def set_active_stages(self, stages: Iterable[str]) -> None:
        """Show only the stages this run will actually go through."""

        wanted = set(stages)
        for stage, holder in self._holders.items():
            holder.setVisible(stage in wanted)

    def reset(self) -> None:
        for stage in self._rows:
            self.set_state(stage, "pending")

    def retheme(self) -> None:
        for stage, state in list(self._states.items()):
            self.set_state(stage, state)

    def set_state(self, stage: str, state: str) -> None:
        entry = self._rows.get(stage)
        if not entry:
            return
        self._states[stage] = state
        marker, text = entry
        colors = theme.active_palette()

        if state == "done":
            marker.setPixmap(icons.pixmap("check", 16, colors.success))
            text.setStyleSheet(f"color: {colors.text_muted};")
        elif state == "active":
            marker.setPixmap(icons.pixmap("play", 14, colors.accent))
            text.setStyleSheet(f"color: {colors.accent}; font-weight: 600;")
        elif state == "failed":
            marker.setPixmap(icons.pixmap("alert", 16, colors.danger))
            text.setStyleSheet(f"color: {colors.danger};")
        else:
            dot = QtGui.QPixmap(16, 16)
            dot.fill(QtCore.Qt.transparent)
            painter = QtGui.QPainter(dot)
            painter.setRenderHint(QtGui.QPainter.Antialiasing)
            painter.setPen(QtGui.QPen(QtGui.QColor(colors.border_strong), 1.6))
            painter.drawEllipse(QtCore.QPointF(8, 8), 4.5, 4.5)
            painter.end()
            marker.setPixmap(dot)
            text.setStyleSheet(f"color: {colors.text_faint};")


class PageHeader(QtWidgets.QWidget):
    """Title, subtitle and an optional row of actions at the top of each page."""

    def __init__(self, title: str, subtitle: str = "", parent: QtWidgets.QWidget | None = None):
        super().__init__(parent)
        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)

        text_box = QtWidgets.QVBoxLayout()
        text_box.setSpacing(3)
        text_box.addWidget(label(title, "PageTitle"))
        self._subtitle = label(subtitle, "PageSubtitle")
        self._subtitle.setVisible(bool(subtitle))
        text_box.addWidget(self._subtitle)
        layout.addLayout(text_box, 1)

        self.actions = QtWidgets.QHBoxLayout()
        self.actions.setSpacing(8)
        layout.addLayout(self.actions, 0)

    def set_subtitle(self, text: str) -> None:
        self._subtitle.setText(text)
        self._subtitle.setVisible(bool(text))

    def add_action(self, widget: QtWidgets.QWidget) -> None:
        self.actions.addWidget(widget, 0, QtCore.Qt.AlignVCenter)


class ScrollPage(QtWidgets.QWidget):
    """Page scaffold: fixed header plus a scrolling column of cards."""

    def __init__(self, title: str, subtitle: str = "", parent: QtWidgets.QWidget | None = None):
        super().__init__(parent)
        outer = QtWidgets.QVBoxLayout(self)
        outer.setContentsMargins(28, 24, 28, 20)
        outer.setSpacing(18)

        self.header = PageHeader(title, subtitle)
        outer.addWidget(self.header)

        scroll = QtWidgets.QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        outer.addWidget(scroll, 1)

        container = QtWidgets.QWidget()
        self.content = QtWidgets.QVBoxLayout(container)
        self.content.setContentsMargins(0, 0, 8, 4)
        self.content.setSpacing(16)
        scroll.setWidget(container)


def _pretty_size(num_bytes: float | None) -> str:
    from ..runtime.store import human_size

    return human_size(num_bytes)


def browse_files(parent: QtWidgets.QWidget, title: str = "Choose media files") -> list[str]:
    media = (
        "Media files (*.mp4 *.mkv *.webm *.mov *.avi *.flac *.mp3 *.wav *.m4a *.mka);;"
        "All files (*)"
    )
    paths, _ = QtWidgets.QFileDialog.getOpenFileNames(parent, title, "", media)
    return paths


def reveal(path: Path | str) -> None:
    """Open a file's folder in the platform file manager."""

    target = Path(path)
    if target.is_file():
        target = target.parent
    if not target.exists():
        return
    QtGui.QDesktopServices.openUrl(QtCore.QUrl.fromLocalFile(str(target)))
