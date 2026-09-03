"""Review page: read the transcript with the recording playing alongside it.

Clicking a line jumps the audio to the moment it was said. That is the only
way to settle the two questions a transcript cannot answer on its own — who
this "Interlocutor 3" actually is, and whether a passage the recogniser was
unsure about really says what it says.
"""
from __future__ import annotations

from pathlib import Path

from jp2subs.gui.common import Card, label
from PySide6 import QtCore, QtWidgets

from ... import review as review_module
from ...model import Transcript
from ...progress import format_stamp
from ..widgets import open_folder

try:  # pragma: no cover - depends on how Qt was packaged
    from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer

    AUDIO_AVAILABLE = True
except Exception:  # pragma: no cover - a build without the multimedia module
    QAudioOutput = QMediaPlayer = None  # type: ignore[assignment]
    AUDIO_AVAILABLE = False

#: Playback speeds offered. Reviewing two hours at 1x is nobody's idea of fun.
SPEEDS = (0.75, 1.0, 1.25, 1.5, 2.0)


class ReviewPage(QtWidgets.QWidget):
    """The transcript as a list, wired to the recording."""

    def __init__(self, parent: QtWidgets.QWidget | None = None):
        super().__init__(parent)
        self.review: review_module.Review | None = None
        self._player = None
        self._audio_out = None
        self._following = True
        self._current_row = -1
        #: A seek asked for before the file finished loading, applied once it has.
        self._pending_seek: int | None = None

        outer = QtWidgets.QVBoxLayout(self)
        outer.setContentsMargins(28, 24, 28, 20)
        outer.setSpacing(14)

        outer.addLayout(self._build_header())
        outer.addWidget(self._build_player_card())
        outer.addWidget(self._build_search())
        outer.addWidget(self._build_list(), 1)

        self._build_player()
        self._show_empty()

    # -- construction -----------------------------------------------------

    def _build_header(self) -> QtWidgets.QHBoxLayout:
        row = QtWidgets.QHBoxLayout()
        row.setSpacing(12)

        titles = QtWidgets.QVBoxLayout()
        titles.setSpacing(3)
        titles.addWidget(label("Revisar", "PageTitle"))
        self.subtitle = label("Clique em uma fala para ouvir aquele momento.", "PageSubtitle")
        titles.addWidget(self.subtitle)
        row.addLayout(titles, 1)

        open_btn = QtWidgets.QPushButton("Abrir transcrição...")
        open_btn.clicked.connect(self.open_transcript)
        row.addWidget(open_btn, 0, QtCore.Qt.AlignVCenter)
        return row

    def _build_player_card(self) -> Card:
        card = Card()
        row = QtWidgets.QHBoxLayout()
        row.setSpacing(10)

        self.play_btn = QtWidgets.QPushButton("Tocar")
        self.play_btn.setObjectName("Primary")
        self.play_btn.setMinimumWidth(96)
        self.play_btn.clicked.connect(self.toggle_play)
        row.addWidget(self.play_btn, 0)

        self.position_slider = QtWidgets.QSlider(QtCore.Qt.Horizontal)
        self.position_slider.setRange(0, 0)
        self.position_slider.sliderMoved.connect(self._seek_ms)
        row.addWidget(self.position_slider, 1)

        self.clock = label("00:00:00", "Faint")
        self.clock.setMinimumWidth(72)
        row.addWidget(self.clock, 0)

        self.speed_combo = QtWidgets.QComboBox()
        for speed in SPEEDS:
            self.speed_combo.addItem(f"{speed:g}×".replace(".", ","), speed)
        self.speed_combo.setCurrentIndex(SPEEDS.index(1.0))
        self.speed_combo.activated.connect(self._on_speed)
        row.addWidget(self.speed_combo, 0)

        self.follow_check = QtWidgets.QCheckBox("Acompanhar")
        self.follow_check.setChecked(True)
        self.follow_check.setToolTip("Rolar a lista sozinho, seguindo o que está tocando.")
        self.follow_check.toggled.connect(self._on_follow)
        row.addWidget(self.follow_check, 0)

        card.body.addLayout(row)
        self.audio_note = label("", "Faint")
        card.body.addWidget(self.audio_note)
        return card

    def _build_search(self) -> QtWidgets.QWidget:
        holder = QtWidgets.QWidget()
        row = QtWidgets.QHBoxLayout(holder)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(8)
        self.search_edit = QtWidgets.QLineEdit()
        self.search_edit.setPlaceholderText("Procurar no texto — mostra só as falas que contêm o termo")
        self.search_edit.setClearButtonEnabled(True)
        self.search_edit.textChanged.connect(self._filter)
        row.addWidget(self.search_edit, 1)
        self.match_label = label("", "Faint")
        row.addWidget(self.match_label, 0)
        return holder

    def _build_list(self) -> QtWidgets.QListWidget:
        self.list = QtWidgets.QListWidget()
        self.list.setObjectName("DropList")
        self.list.setWordWrap(True)
        self.list.setAlternatingRowColors(False)
        self.list.setSelectionMode(QtWidgets.QAbstractItemView.SingleSelection)
        # Only a real click seeks. Selecting from code, as the highlight
        # follows the audio, must not drag the playhead back with it.
        self.list.itemClicked.connect(self._on_item_clicked)
        self.list.itemActivated.connect(self._on_item_clicked)
        return self.list

    def _build_player(self) -> None:
        if not AUDIO_AVAILABLE:
            self.audio_note.setText(
                "Esta instalação não tem o componente de áudio do Qt, então a lista "
                "funciona mas não dá para ouvir. Os horários continuam servindo para "
                "achar o trecho no seu player."
            )
            for widget in (self.play_btn, self.position_slider, self.speed_combo, self.follow_check):
                widget.setEnabled(False)
            return

        self._player = QMediaPlayer(self)
        self._audio_out = QAudioOutput(self)
        self._player.setAudioOutput(self._audio_out)
        self._player.positionChanged.connect(self._on_position)
        self._player.mediaStatusChanged.connect(self._on_media_status)
        self._player.durationChanged.connect(self._on_duration)
        self._player.playbackStateChanged.connect(self._on_state)
        self._player.errorOccurred.connect(self._on_error)

    # -- loading ----------------------------------------------------------

    def load_transcript(self, transcript: Transcript) -> None:
        """Show a run that just finished."""

        self.show_review(review_module.from_transcript(transcript))

    def open_transcript(self) -> None:
        chosen, _filter = QtWidgets.QFileDialog.getOpenFileName(
            self, "Abrir uma transcrição", "", "Transcrição (*.json);;Todos os arquivos (*)"
        )
        if not chosen:
            return
        try:
            review = review_module.from_json(chosen)
        except (OSError, ValueError) as exc:
            QtWidgets.QMessageBox.warning(self, "Não deu para abrir", str(exc))
            return
        self.show_review(review)

    def show_review(self, review: review_module.Review) -> None:
        self.review = review
        self._current_row = -1
        self.list.clear()
        self.search_edit.clear()

        for index, turn in enumerate(review.turns):
            head = format_stamp(turn.start)
            who = f" · {turn.speaker}" if turn.speaker else ""
            doubt = "  [?]" if turn.uncertain else ""
            item = QtWidgets.QListWidgetItem(f"{head}{who}{doubt}\n{turn.text}")
            item.setData(QtCore.Qt.UserRole, index)
            self.list.addItem(item)

        count = len(review.turns)
        self.subtitle.setText(
            f"{review.title or 'Transcrição'} · {count} falas · clique em uma para ouvir aquele momento."
        )
        self._load_audio()
        self._filter(self.search_edit.text())

    def _load_audio(self) -> None:
        if not self._player or not self.review:
            return
        if not self.review.has_audio:
            self.audio_note.setText(
                "A gravação não foi encontrada onde ela estava quando a transcrição "
                "foi feita. Coloque o arquivo de áudio na mesma pasta do .json para "
                "poder ouvir."
            )
            self.play_btn.setEnabled(False)
            self.position_slider.setEnabled(False)
            return
        self.audio_note.setText("")
        self.play_btn.setEnabled(True)
        self.position_slider.setEnabled(True)
        self._pending_seek = None
        self._player.setSource(QtCore.QUrl.fromLocalFile(str(self.review.source)))

    def _show_empty(self) -> None:
        self.list.clear()
        placeholder = QtWidgets.QListWidgetItem(
            "Nenhuma transcrição aberta.\n"
            "Transcreva uma reunião ou use “Abrir transcrição...” para carregar um .json já feito."
        )
        placeholder.setFlags(QtCore.Qt.NoItemFlags)
        self.list.addItem(placeholder)
        self.play_btn.setEnabled(False)
        self.position_slider.setEnabled(False)

    # -- playback ---------------------------------------------------------

    def toggle_play(self) -> None:
        if not self._player:
            return
        if self._player.playbackState() == QMediaPlayer.PlayingState:
            self._player.pause()
        else:
            self._player.play()

    def _on_item_clicked(self, item: QtWidgets.QListWidgetItem) -> None:
        index = item.data(QtCore.Qt.UserRole)
        if index is None or not self.review:
            return
        turn = self.review.turns[int(index)]
        if not self._player or not self.review.has_audio:
            return
        self._seek_ms(int(turn.start * 1000))
        self._player.play()

    def _seek_ms(self, milliseconds: int) -> None:
        """Jump to a moment, even if the recording is still opening.

        Loading is asynchronous, and a position set before the file is ready is
        silently dropped — which, on the very first click after a transcription
        finishes, is exactly when it would happen.
        """

        if not self._player:
            return
        target = int(milliseconds)
        if self._player.isSeekable():
            self._player.setPosition(target)
            self._pending_seek = None
        else:
            self._pending_seek = target

    def _on_media_status(self, status) -> None:
        ready = status in (
            QMediaPlayer.LoadedMedia,
            QMediaPlayer.BufferedMedia,
            QMediaPlayer.BufferingMedia,
        )
        if ready and self._pending_seek is not None:
            self._player.setPosition(self._pending_seek)
            self._pending_seek = None

    def _on_position(self, milliseconds: int) -> None:
        seconds = milliseconds / 1000.0
        self.clock.setText(format_stamp(seconds))
        if not self.position_slider.isSliderDown():
            self.position_slider.setValue(int(milliseconds))
        if not self._following or not self.review:
            return
        row = self.review.turn_at(seconds)
        if row is None or row == self._current_row:
            return
        self._current_row = row
        item = self._item_for(row)
        if item and not item.isHidden():
            self.list.setCurrentItem(item)
            self.list.scrollToItem(item, QtWidgets.QAbstractItemView.PositionAtCenter)

    def _item_for(self, index: int) -> QtWidgets.QListWidgetItem | None:
        for row in range(self.list.count()):
            item = self.list.item(row)
            if item.data(QtCore.Qt.UserRole) == index:
                return item
        return None

    def _on_duration(self, milliseconds: int) -> None:
        self.position_slider.setRange(0, max(0, int(milliseconds)))

    def _on_state(self, state) -> None:
        playing = state == QMediaPlayer.PlayingState
        self.play_btn.setText("Pausar" if playing else "Tocar")

    def _on_error(self, _error, message: str = "") -> None:
        self.audio_note.setText(
            f"Não deu para tocar este arquivo{': ' + message if message else '.'} "
            "Converta a gravação para .wav ou .mp3 e tente de novo."
        )
        self.play_btn.setEnabled(False)

    def _on_speed(self, index: int) -> None:
        if self._player:
            self._player.setPlaybackRate(float(self.speed_combo.itemData(index)))

    def _on_follow(self, checked: bool) -> None:
        self._following = checked

    # -- search -----------------------------------------------------------

    def _filter(self, term: str) -> None:
        needle = (term or "").strip().lower()
        if not self.review:
            return
        shown = 0
        for row in range(self.list.count()):
            item = self.list.item(row)
            index = item.data(QtCore.Qt.UserRole)
            if index is None:
                continue
            turn = self.review.turns[int(index)]
            matches = not needle or needle in turn.text.lower() or needle in turn.speaker.lower()
            item.setHidden(not matches)
            shown += int(matches)
        self.match_label.setText(
            "" if not needle else f"{shown} de {len(self.review.turns)}"
        )

    def reveal_source(self) -> None:
        if self.review and self.review.source:
            open_folder(self.review.source)
