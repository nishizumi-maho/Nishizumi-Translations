"""Review page: read the transcript with the recording playing alongside it.

Clicking a line jumps the audio to the moment it was said. That is the only
way to settle the two questions a transcript cannot answer on its own — who
this "Interlocutor 3" actually is, and whether a passage the recogniser was
unsure about really says what it says.
"""
from __future__ import annotations

from pathlib import Path

from jp2subs.gui.common import Card, Collapsible, label
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
        self._name_edits: list[QtWidgets.QLineEdit] = []
        self._dirty = False

        outer = QtWidgets.QVBoxLayout(self)
        outer.setContentsMargins(28, 24, 28, 20)
        outer.setSpacing(14)

        outer.addLayout(self._build_header())
        outer.addWidget(self._build_player_card())
        outer.addWidget(self._build_speakers_card())
        outer.addWidget(self._build_search())
        outer.addWidget(self._build_list(), 1)
        outer.addWidget(self._build_correction_bar())

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

    def _build_speakers_card(self) -> QtWidgets.QWidget:
        """Names for the voices, editable, with how much each one talked."""

        self.speakers_box = Collapsible("Interlocutores — dê o nome real de cada voz", expanded=True)
        self.speakers_form = QtWidgets.QFormLayout()
        self.speakers_form.setSpacing(6)
        self.speakers_form.setFieldGrowthPolicy(QtWidgets.QFormLayout.AllNonFixedFieldsGrow)
        self.speakers_box.body.addLayout(self.speakers_form)
        self.speakers_hint = label(
            "Clique numa fala para ouvir quem é, e escreva o nome aqui. Ele passa a "
            "valer em todas as falas daquela voz.",
            "Faint",
        )
        self.speakers_box.body.addWidget(self.speakers_hint)
        return self.speakers_box

    def _build_correction_bar(self) -> QtWidgets.QWidget:
        holder = QtWidgets.QWidget()
        row = QtWidgets.QHBoxLayout(holder)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(8)

        row.addWidget(label("Esta fala é de:", "Faint"), 0)
        self.reassign_combo = QtWidgets.QComboBox()
        self.reassign_combo.setMinimumWidth(220)
        self.reassign_combo.activated.connect(self._reassign_selected)
        row.addWidget(self.reassign_combo, 0)

        row.addStretch(1)
        self.save_btn = QtWidgets.QPushButton("Salvar correções")
        self.save_btn.setObjectName("Primary")
        self.save_btn.setToolTip(
            "Regrava a transcrição com os nomes e as correções, por cima dos "
            "arquivos que você abriu."
        )
        self.save_btn.clicked.connect(self._save_corrections)
        row.addWidget(self.save_btn, 0)
        self._correction_bar = holder
        return holder

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
            item = QtWidgets.QListWidgetItem(self._row_text(turn))
            item.setData(QtCore.Qt.UserRole, index)
            self.list.addItem(item)

        self._dirty = False
        self._rebuild_speaker_editors()
        count = len(review.turns)
        self.subtitle.setText(
            f"{review.title or 'Transcrição'} · {count} falas · clique em uma para ouvir aquele momento."
        )
        self._load_audio()
        self._filter(self.search_edit.text())

    def _rebuild_speaker_editors(self) -> None:
        """One name field per voice, ordered by how much each of them talked."""

        while self.speakers_form.rowCount():
            self.speakers_form.removeRow(0)
        self._name_edits = []
        self.reassign_combo.clear()

        review = self.review
        editable = bool(review and review.diarized and review.talk_time())
        self.speakers_box.setVisible(bool(editable))
        self._correction_bar.setVisible(bool(editable))
        if not editable or review is None:
            return

        for index, name, seconds in review.talk_time():
            edit = QtWidgets.QLineEdit(name)
            edit.setPlaceholderText(f"Nome do interlocutor {index + 1}")
            edit.editingFinished.connect(
                lambda position=index, widget=edit: self._rename(position, widget.text())
            )
            self.speakers_form.addRow(f"{format_stamp(seconds)} de fala", edit)
            self._name_edits.append(edit)
            self.reassign_combo.addItem(name, index)
        self.reassign_combo.addItem("Não identificado", None)
        self.save_btn.setEnabled(bool(review.path))
        if not review.path:
            self.save_btn.setToolTip(
                "Esta transcrição ainda não foi aberta de um arquivo. Use "
                "“Abrir transcrição...” para poder regravar as correções."
            )

    def _rename(self, index: int, name: str) -> None:
        if not self.review:
            return
        if self.review.name_for(index) == name.strip():
            return
        self.review.rename_speaker(index, name)
        self._dirty = True
        self._refresh_rows()
        self._refresh_combo_names()

    def _refresh_combo_names(self) -> None:
        if not self.review:
            return
        for position in range(self.reassign_combo.count()):
            index = self.reassign_combo.itemData(position)
            if index is not None:
                self.reassign_combo.setItemText(position, self.review.name_for(int(index)))

    def _refresh_rows(self) -> None:
        """Redraw the visible text of every line, keeping hidden state."""

        if not self.review:
            return
        for row in range(self.list.count()):
            item = self.list.item(row)
            index = item.data(QtCore.Qt.UserRole)
            if index is None:
                continue
            item.setText(self._row_text(self.review.turns[int(index)]))

    def _reassign_selected(self, position: int) -> None:
        item = self.list.currentItem()
        if not item or not self.review:
            return
        index = item.data(QtCore.Qt.UserRole)
        if index is None:
            return
        speaker = self.reassign_combo.itemData(position)
        self.review.reassign(int(index), None if speaker is None else int(speaker))
        self._dirty = True
        self._refresh_rows()
        self._rebuild_speaker_editors()

    def _save_corrections(self) -> None:
        if not self.review:
            return
        try:
            written = review_module.save(self.review)
        except (OSError, ValueError) as exc:
            QtWidgets.QMessageBox.warning(self, "Não deu para salvar", str(exc))
            return
        self._dirty = False
        QtWidgets.QMessageBox.information(
            self,
            "Correções salvas",
            "Regravado:\n" + "\n".join(item.name for item in written),
        )

    def _row_text(self, turn) -> str:
        head = format_stamp(turn.start)
        who = f" · {turn.speaker}" if turn.speaker else ""
        doubt = "  [?]" if turn.uncertain else ""
        return f"{head}{who}{doubt}\n{turn.text}"

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
        position = self.reassign_combo.findData(turn.speaker_index)
        if position >= 0:
            self.reassign_combo.setCurrentIndex(position)
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
