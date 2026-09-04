"""The page the app exists for: drop a recording in, get a transcript out."""
from __future__ import annotations

from pathlib import Path

from jp2subs.gui.common import Banner, Card, Collapsible, FileQueue, ScrollPage, hline, label
from PySide6 import QtCore, QtWidgets

from ... import components, languages
from ...config import (
    DEFAULT_PROMPT,
    TREATMENTS,
    Settings,
    load_settings,
    parse_glossary,
    parse_speaker_names,
    save_settings,
)
from ...diarize import DEFAULT_THRESHOLD, THRESHOLD_CHOICES, unavailable_reason
from ...media import is_media
from ...pipeline import Job, Result, TrackJob
from ...progress import ProgressEvent
from ..widgets import DropZone, browse_recordings, open_file, open_folder
from ..workers import AnalysisWorker, TranscriptionWorker


class TranscribePage(ScrollPage):
    """Queue, options, progress, and the buttons that start and stop a run."""

    #: Asks the window to switch pages, e.g. to Componentes.
    navigate = QtCore.Signal(str)
    #: A finished Transcript, for the Review page to open.
    transcript_ready = QtCore.Signal(object)

    def __init__(self, parent: QtWidgets.QWidget | None = None):
        super().__init__(
            "Transcrever",
            "Áudio da reunião em texto, com horários e interlocutores.",
            parent,
        )
        self.settings: Settings = load_settings()
        self._worker: TranscriptionWorker | None = None
        self._queue: list[Path] = []
        self._results: list[Result] = []

        self._build_banner()
        self._build_sources_card()
        self._build_options_card()
        self._build_run_card()
        self.content.addStretch(1)

        self._load_settings_into_form()
        self.refresh_components()

    # -- construction -----------------------------------------------------

    def _build_banner(self) -> None:
        self.banner = Banner("", "warning", "Abrir Componentes")
        self.banner.action_clicked.connect(lambda: self.navigate.emit("componentes"))
        self.banner.setVisible(False)
        self.content.addWidget(self.banner)

    def _build_sources_card(self) -> None:
        card = Card("Gravação", "Uma ou várias. Elas são transcritas na ordem.", icon_name="waveform")

        self.drop_zone = DropZone()
        self.drop_zone.files_dropped.connect(self._add_paths)
        self.drop_zone.browse_requested.connect(self._browse)
        card.body.addWidget(self.drop_zone)

        # Both stay hidden until there is something queued: an empty list box
        # under the drop zone is just a hole in the page.
        self.queue = FileQueue()
        self.queue.setMaximumHeight(150)
        self.queue.files_dropped.connect(self._add_paths)
        self.queue.model().rowsInserted.connect(self._sync_queue_visibility)
        self.queue.model().rowsRemoved.connect(self._sync_queue_visibility)
        card.body.addWidget(self.queue)

        self.queue_buttons = QtWidgets.QWidget()
        row = QtWidgets.QHBoxLayout(self.queue_buttons)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(8)
        remove = QtWidgets.QPushButton("Remover selecionados")
        remove.clicked.connect(self._remove_selected)
        clear = QtWidgets.QPushButton("Limpar lista")
        clear.clicked.connect(self._clear_queue)
        self.analyse_btn = QtWidgets.QPushButton("Analisar o áudio")
        self.analyse_btn.setToolTip(
            "Mede a gravação e diz quais ajustes de áudio valem a pena para ela, "
            "antes de gastar uma hora transcrevendo."
        )
        self.analyse_btn.clicked.connect(self._analyse)
        row.addWidget(remove)
        row.addWidget(clear)
        row.addWidget(self.analyse_btn)
        row.addStretch(1)
        card.body.addWidget(self.queue_buttons)
        self._sync_queue_visibility()

        self.content.addWidget(card)

    def _build_options_card(self) -> None:
        card = Card("Como transcrever", "", icon_name="sliders")

        form = QtWidgets.QFormLayout()
        form.setSpacing(11)
        form.setLabelAlignment(QtCore.Qt.AlignLeft)
        form.setFieldGrowthPolicy(QtWidgets.QFormLayout.AllNonFixedFieldsGrow)

        self.model_combo = QtWidgets.QComboBox()
        self.model_combo.setMinimumWidth(300)
        self.model_combo.activated.connect(self._on_model_activated)
        form.addRow("Modelo", self.model_combo)

        # Editable on purpose: the four presets cover almost everything, and
        # anything else Whisper knows is one typed code away.
        self.language_combo = QtWidgets.QComboBox()
        self.language_combo.setEditable(True)
        self.language_combo.setInsertPolicy(QtWidgets.QComboBox.NoInsert)
        for item in languages.PRESETS:
            self.language_combo.addItem(item.label, item.code)
        self.language_combo.setToolTip(
            "A fala da reunião, não a interface. Dá para digitar qualquer código "
            "do Whisper (ja, fr, de, it...). 'pt' cobre o português do Brasil."
        )
        form.addRow("Idioma da fala", self.language_combo)

        self.tracks_check = QtWidgets.QCheckBox("Cada arquivo é um participante (uma faixa por pessoa)")
        self.tracks_check.setToolTip(
            "Para gravações do Teams, Meet ou Zoom exportadas com uma faixa por "
            "pessoa. A fila inteira vira uma reunião só, e quem falou vem do "
            "arquivo — sem separação de vozes, sem erro de atribuição."
        )
        self.tracks_check.toggled.connect(self._on_tracks_toggled)
        form.addRow("Faixas", self.tracks_check)

        self.speakers_check = QtWidgets.QCheckBox("Identificar quem falou cada trecho")
        self.speakers_check.toggled.connect(self._on_speakers_toggled)
        form.addRow("Interlocutores", self.speakers_check)

        # The number of people is found from how readily two stretches of
        # speech count as one voice, not stated up front — see diarize.py for
        # why pinning a headcount measures worse than it sounds.
        self.separation_combo = QtWidgets.QComboBox()
        for text, value in THRESHOLD_CHOICES:
            self.separation_combo.addItem(text, value)
        self.separation_combo.setToolTip(
            "Mude só se o resultado sair errado: se duas pessoas viraram uma, "
            "separe mais; se uma pessoa virou duas, junte mais."
        )
        form.addRow("Separação de vozes", self.separation_combo)

        self.names_edit = QtWidgets.QLineEdit()
        self.names_edit.setPlaceholderText("Ana, João, Carla — na ordem em que falam pela primeira vez")
        form.addRow("Quem é quem", self.names_edit)

        self.glossary_edit = QtWidgets.QPlainTextEdit()
        self.glossary_edit.setMaximumHeight(84)
        self.glossary_edit.setPlaceholderText(
            "Um por linha: nomes de pessoas, projetos, clientes e siglas da empresa"
        )
        self.glossary_edit.setToolTip(
            "O reconhecimento recebe esta lista como dica, e depois a grafia é "
            "conferida contra ela. É o que mais melhora nome próprio e sigla, "
            "que é justamente o que uma ata precisa acertar."
        )
        form.addRow("Glossário", self.glossary_edit)

        self.layout_combo = QtWidgets.QComboBox()
        self.layout_combo.addItem("Blocos (horário, nome, fala)", "blocos")
        self.layout_combo.addItem("Uma linha por fala", "linhas")
        form.addRow("Formato do texto", self.layout_combo)

        extras = QtWidgets.QHBoxLayout()
        extras.setSpacing(14)
        self.srt_check = QtWidgets.QCheckBox("Legenda .srt")
        self.vtt_check = QtWidgets.QCheckBox("Legenda .vtt")
        self.json_check = QtWidgets.QCheckBox("Dados .json")
        for widget in (self.srt_check, self.vtt_check, self.json_check):
            extras.addWidget(widget)
        extras.addStretch(1)
        form.addRow("Salvar também", extras)

        output_row = QtWidgets.QHBoxLayout()
        output_row.setSpacing(8)
        self.output_edit = QtWidgets.QLineEdit()
        self.output_edit.setPlaceholderText("Automático: na mesma pasta da gravação")
        browse = QtWidgets.QPushButton("Escolher")
        browse.clicked.connect(self._choose_output)
        output_row.addWidget(self.output_edit, 1)
        output_row.addWidget(browse, 0)
        form.addRow("Salvar em", output_row)

        card.body.addLayout(form)
        card.body.addWidget(hline())
        card.body.addWidget(self._build_advanced())
        self.content.addWidget(card)

    def _build_advanced(self) -> Collapsible:
        advanced = Collapsible("Ajustes avançados")
        form = QtWidgets.QFormLayout()
        form.setSpacing(10)
        form.setFieldGrowthPolicy(QtWidgets.QFormLayout.AllNonFixedFieldsGrow)

        self.device_combo = QtWidgets.QComboBox()
        self.device_combo.addItem("Automático (GPU quando houver)", "auto")
        self.device_combo.addItem("Placa de vídeo (CUDA)", "cuda")
        self.device_combo.addItem("Processador", "cpu")
        form.addRow("Processamento", self.device_combo)

        self.beam_spin = QtWidgets.QSpinBox()
        self.beam_spin.setRange(1, 20)
        form.addRow("Beam size", self.beam_spin)

        self.vad_check = QtWidgets.QCheckBox("Pular os silêncios antes de transcrever")
        form.addRow("Silêncios", self.vad_check)

        self.repetition_check = QtWidgets.QCheckBox(
            "Evitar repetições em gravações longas"
        )
        self.repetition_check.setToolTip(
            "Reinicia o contexto do Whisper a cada trecho. Recomendado em reuniões longas."
        )
        form.addRow("Estabilidade", self.repetition_check)

        self.threads_spin = QtWidgets.QSpinBox()
        self.threads_spin.setRange(0, 64)
        self.threads_spin.setSpecialValueText("Automático")
        form.addRow("Núcleos de CPU", self.threads_spin)

        self.compute_combo = QtWidgets.QComboBox()
        self.compute_combo.addItem("Padrão", "")
        for value in ("float16", "int8", "int8_float16"):
            self.compute_combo.addItem(value, value)
        form.addRow("Precisão", self.compute_combo)

        self.gap_spin = QtWidgets.QDoubleSpinBox()
        self.gap_spin.setRange(0.0, 10.0)
        self.gap_spin.setSingleStep(0.2)
        self.gap_spin.setSuffix(" s")
        self.gap_spin.setToolTip("Pausa máxima para juntar duas falas seguidas da mesma pessoa.")
        form.addRow("Juntar falas até", self.gap_spin)

        self.treatment_combo = QtWidgets.QComboBox()
        for code, label in TREATMENTS:
            self.treatment_combo.addItem(label, code)
        self.treatment_combo.setToolTip(
            "No automático, o aplicativo mede a gravação antes de transcrever e "
            "aplica o que ela pedir: equalização sempre, e nivelamento das vozes "
            "distantes só quando a medição mostrar que faz falta."
        )
        form.addRow("Tratamento do áudio", self.treatment_combo)

        self.uncertain_check = QtWidgets.QCheckBox("Marcar com [?] o que saiu duvidoso")
        form.addRow("Dúvidas", self.uncertain_check)

        self.repetition_filter_check = QtWidgets.QCheckBox("Descartar trechos repetidos em loop")
        form.addRow("Repetições", self.repetition_filter_check)

        self.reuse_check = QtWidgets.QCheckBox("Reaproveitar transcrição já feita do mesmo arquivo")
        self.reuse_check.setToolTip(
            "Guarda o reconhecimento assim que ele termina. Repetir a mesma "
            "gravação com os mesmos ajustes pula a parte que leva horas."
        )
        form.addRow("Reaproveitar", self.reuse_check)

        self.prompt_edit = QtWidgets.QPlainTextEdit()
        self.prompt_edit.setMaximumHeight(70)
        self.prompt_edit.setPlaceholderText(DEFAULT_PROMPT)
        self.language_combo.currentTextChanged.connect(self._sync_prompt_placeholder)
        self.prompt_edit.setToolTip(
            "Contexto dado ao Whisper. Inclua nomes próprios e siglas da empresa "
            "para ele acertar a grafia."
        )
        form.addRow("Contexto", self.prompt_edit)

        advanced.body.addLayout(form)
        return advanced

    def _build_run_card(self) -> None:
        card = Card("Andamento", "", icon_name="play")

        buttons = QtWidgets.QHBoxLayout()
        buttons.setSpacing(10)
        self.start_btn = QtWidgets.QPushButton("Transcrever")
        self.start_btn.setObjectName("Primary")
        self.start_btn.setMinimumHeight(38)
        self.start_btn.clicked.connect(self.start)
        buttons.addWidget(self.start_btn, 1)

        self.cancel_btn = QtWidgets.QPushButton("Cancelar")
        self.cancel_btn.setMinimumHeight(38)
        self.cancel_btn.setEnabled(False)
        self.cancel_btn.clicked.connect(self.cancel)
        buttons.addWidget(self.cancel_btn, 0)
        card.body.addLayout(buttons)

        self.progress = QtWidgets.QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        card.body.addWidget(self.progress)

        self.stage_label = label("Pronto para começar.", "CardHint")
        card.body.addWidget(self.stage_label)
        self.detail_label = label("", "Faint")
        card.body.addWidget(self.detail_label)

        self.log = QtWidgets.QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setMaximumHeight(150)
        card.body.addWidget(self.log)

        result_row = QtWidgets.QHBoxLayout()
        result_row.setSpacing(8)
        self.open_text_btn = QtWidgets.QPushButton("Abrir a transcrição")
        self.open_text_btn.clicked.connect(self._open_text)
        self.open_folder_btn = QtWidgets.QPushButton("Abrir a pasta")
        self.open_folder_btn.clicked.connect(self._open_folder)
        self.review_btn = QtWidgets.QPushButton("Revisar ouvindo")
        self.review_btn.setToolTip("Ler a transcrição com a gravação tocando junto.")
        self.review_btn.clicked.connect(lambda: self.navigate.emit("revisar"))
        for button in (self.open_text_btn, self.open_folder_btn, self.review_btn):
            button.setEnabled(False)
            result_row.addWidget(button)
        result_row.addStretch(1)
        card.body.addLayout(result_row)

        self.content.addWidget(card)

    # -- settings <-> form ------------------------------------------------

    def _load_settings_into_form(self) -> None:
        settings = self.settings
        index = self.language_combo.findData(settings.language)
        if index >= 0:
            self.language_combo.setCurrentIndex(index)
        else:
            self.language_combo.setEditText(settings.language)
        self.tracks_check.setChecked(settings.tracks_are_speakers)
        self.speakers_check.setChecked(settings.identify_speakers)
        index = self.separation_combo.findData(settings.clustering_threshold)
        self.separation_combo.setCurrentIndex(index if index >= 0 else 0)
        self.names_edit.setText(", ".join(settings.speaker_names))
        self.glossary_edit.setPlainText("\n".join(settings.glossary))
        self.layout_combo.setCurrentIndex(max(0, self.layout_combo.findData(settings.layout)))
        self.srt_check.setChecked(settings.also_srt)
        self.vtt_check.setChecked(settings.also_vtt)
        self.json_check.setChecked(settings.also_json)
        self.output_edit.setText(settings.output_dir)
        self.device_combo.setCurrentIndex(max(0, self.device_combo.findData(settings.device)))
        self.beam_spin.setValue(settings.beam_size)
        self.vad_check.setChecked(settings.vad)
        self.repetition_check.setChecked(settings.avoid_repetition)
        self.threads_spin.setValue(settings.threads)
        self.compute_combo.setCurrentIndex(max(0, self.compute_combo.findData(settings.compute_type)))
        self.gap_spin.setValue(settings.merge_gap)
        index = self.treatment_combo.findData(settings.audio_treatment)
        self.treatment_combo.setCurrentIndex(index if index >= 0 else 0)
        self.uncertain_check.setChecked(settings.mark_uncertain)
        self.repetition_filter_check.setChecked(settings.filter_repetitions)
        self.reuse_check.setChecked(settings.reuse_transcription)
        if settings.initial_prompt and settings.initial_prompt != DEFAULT_PROMPT:
            self.prompt_edit.setPlainText(settings.initial_prompt)
        self._on_speakers_toggled(settings.identify_speakers)
        self._on_tracks_toggled(settings.tracks_are_speakers)
        self._sync_prompt_placeholder()

    def _collect_settings(self) -> Settings:
        settings = self.settings
        settings.model = self.model_combo.currentData() or ""
        settings.language = self._chosen_language()
        settings.tracks_are_speakers = self.tracks_check.isChecked()
        settings.identify_speakers = self.speakers_check.isChecked()
        settings.clustering_threshold = self.separation_combo.currentData() or DEFAULT_THRESHOLD
        settings.speaker_names = parse_speaker_names(self.names_edit.text())
        settings.glossary = parse_glossary(self.glossary_edit.toPlainText())
        settings.layout = self.layout_combo.currentData() or "blocos"
        settings.also_srt = self.srt_check.isChecked()
        settings.also_vtt = self.vtt_check.isChecked()
        settings.also_json = self.json_check.isChecked()
        settings.output_dir = self.output_edit.text().strip()
        settings.device = self.device_combo.currentData() or "auto"
        settings.beam_size = self.beam_spin.value()
        settings.vad = self.vad_check.isChecked()
        settings.avoid_repetition = self.repetition_check.isChecked()
        settings.threads = self.threads_spin.value()
        settings.compute_type = self.compute_combo.currentData() or ""
        settings.merge_gap = self.gap_spin.value()
        settings.audio_treatment = self.treatment_combo.currentData() or "auto"
        settings.mark_uncertain = self.uncertain_check.isChecked()
        settings.filter_repetitions = self.repetition_filter_check.isChecked()
        settings.reuse_transcription = self.reuse_check.isChecked()
        settings.initial_prompt = self.prompt_edit.toPlainText().strip() or DEFAULT_PROMPT
        settings.normalize()
        save_settings(settings)
        return settings

    # -- component state --------------------------------------------------

    def refresh_components(self) -> None:
        """Re-read what is installed: the model list and the warnings depend on it."""

        previous = self.model_combo.currentData()
        self.model_combo.clear()
        installed = components.installed_models()
        for item in installed:
            self.model_combo.addItem(item.name, item.model_alias)
        if not installed:
            self.model_combo.addItem("Nenhum modelo baixado ainda", "")
        self.model_combo.addItem("Baixar outro modelo...", "__baixar__")

        wanted = previous or self.settings.model
        index = self.model_combo.findData(wanted)
        self.model_combo.setCurrentIndex(index if index >= 0 else 0)

        self._refresh_banner()

    def _refresh_banner(self) -> None:
        missing = components.missing_essentials()
        if missing:
            names = ", ".join(item.name for item in missing)
            self.banner.set_message(
                f"Ainda falta baixar: {names}. Sem isso a transcrição não roda.",
                "warning",
                "Abrir Componentes",
            )
            self.banner.setVisible(True)
            return

        if self.speakers_check.isChecked():
            reason = unavailable_reason()
            if reason:
                self.banner.set_message(reason, "warning", "Abrir Componentes")
                self.banner.setVisible(True)
                return

        self.banner.setVisible(False)

    def _sync_prompt_placeholder(self, _text: str = "") -> None:
        default = languages.prompt_for(self._chosen_language())
        self.prompt_edit.setPlaceholderText(
            default or "Contexto para o reconhecimento (opcional)"
        )

    def _chosen_language(self) -> str:
        """The code behind the box, whether picked from the list or typed."""

        typed = self.language_combo.currentText().strip()
        index = self.language_combo.findText(typed)
        if index >= 0:
            return str(self.language_combo.itemData(index) or "")
        return languages.normalize(typed)

    def _on_tracks_toggled(self, checked: bool) -> None:
        # With a track per person there is nothing left to tell apart.
        self.speakers_check.setEnabled(not checked)
        self.separation_combo.setEnabled(not checked and self.speakers_check.isChecked())
        self.names_edit.setPlaceholderText(
            "Ana, João, Carla — na ordem dos arquivos na lista"
            if checked
            else "Ana, João, Carla — na ordem em que falam pela primeira vez"
        )

    def _on_speakers_toggled(self, checked: bool) -> None:
        self.separation_combo.setEnabled(checked)
        self.names_edit.setEnabled(checked)
        self._refresh_banner()

    def _on_model_activated(self, index: int) -> None:
        if self.model_combo.itemData(index) == "__baixar__":
            self.refresh_components()
            self.navigate.emit("componentes")

    # -- queue ------------------------------------------------------------

    def _browse(self) -> None:
        self._add_paths(browse_recordings(self))

    def _add_paths(self, paths: list[str]) -> None:
        ignored = []
        for raw in paths:
            path = Path(raw)
            if path.is_dir():
                for child in sorted(path.iterdir()):
                    if child.is_file() and is_media(child):
                        self.queue.add_path(str(child))
                continue
            if not is_media(path):
                ignored.append(path.name)
                continue
            self.queue.add_path(str(path))
        if ignored:
            QtWidgets.QMessageBox.information(
                self,
                "Arquivo ignorado",
                "Estes arquivos não são áudio nem vídeo:\n" + "\n".join(ignored),
            )

    def _sync_queue_visibility(self, *_args) -> None:
        has_items = self.queue.count() > 0
        self.queue.setVisible(has_items)
        self.queue_buttons.setVisible(has_items)

    def _analyse(self) -> None:
        """Measure the first queued recording and say what it needs."""

        paths = self.queue.paths()
        if not paths:
            QtWidgets.QMessageBox.information(
                self, "Nenhuma gravação", "Arraste o arquivo da reunião para analisar."
            )
            return

        self.analyse_btn.setEnabled(False)
        self.analyse_btn.setText("Analisando...")
        worker = AnalysisWorker(paths[0])
        worker.signals.finished.connect(self._on_analysis)
        worker.signals.failed.connect(self._on_analysis_failed)
        QtCore.QThreadPool.globalInstance().start(worker)

    @QtCore.Slot(object, object)
    def _on_analysis(self, _found, advice) -> None:
        """Show the measurements, and say plainly what they will and will not do.

        Measuring changes nothing on its own, and a window full of numbers that
        closes on OK reads as though something was applied. It has to say which
        treatments are actually switched on for the next run.
        """

        self._reset_analyse_button()
        lines = list(advice.lines)
        mode = self.treatment_combo.currentData() or "auto"
        lines.append("")
        lines.append("Medir não altera a gravação: o tratamento vai numa cópia,")
        lines.append("na hora de transcrever.")
        lines.append("")
        if mode == "auto":
            lines.append(
                "Tratamento em AUTOMÁTICO: ao transcrever, o aplicativo repete esta"
            )
            lines.append("medição e aplica exatamente o que ela indicar acima.")
        else:
            lines.append(
                f"Tratamento fixo em “{self.treatment_combo.currentText()}”, "
                "independentemente desta medição."
            )

        box = QtWidgets.QMessageBox(self)
        box.setWindowTitle("Análise da gravação")
        box.setIcon(QtWidgets.QMessageBox.Information)
        box.setText("\n".join(lines))

        if advice.recommend_dynamic and mode not in {"auto", "nivelar"}:
            box.setInformativeText(
                "Esta gravação pede nivelamento das vozes distantes, mas o "
                "tratamento está fixo e não vai aplicá-lo. Quer voltar para o "
                "automático?"
            )
            box.setStandardButtons(QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No)
            box.setDefaultButton(QtWidgets.QMessageBox.Yes)
            if box.exec() == QtWidgets.QMessageBox.Yes:
                self.treatment_combo.setCurrentIndex(
                    max(0, self.treatment_combo.findData("auto"))
                )
            return
        box.exec()

    def _on_analysis_failed(self, message: str) -> None:
        self._reset_analyse_button()
        QtWidgets.QMessageBox.warning(self, "Não deu para analisar", message)

    def _reset_analyse_button(self) -> None:
        self.analyse_btn.setEnabled(True)
        self.analyse_btn.setText("Analisar o áudio")

    def _remove_selected(self) -> None:
        for item in self.queue.selectedItems():
            self.queue.takeItem(self.queue.row(item))

    def _clear_queue(self) -> None:
        self.queue.clear()

    def _choose_output(self) -> None:
        chosen = QtWidgets.QFileDialog.getExistingDirectory(
            self, "Escolher onde salvar a transcrição", self.output_edit.text()
        )
        if chosen:
            self.output_edit.setText(chosen)

    # -- running ----------------------------------------------------------

    def start(self) -> None:
        if self._worker is not None:
            return
        paths = self.queue.paths()
        if not paths:
            QtWidgets.QMessageBox.information(
                self, "Nenhuma gravação", "Arraste o arquivo da reunião para começar."
            )
            return
        missing = components.missing_essentials()
        if missing:
            self.navigate.emit("componentes")
            return

        settings = self._collect_settings()
        if not settings.model and not components.installed_models():
            self.navigate.emit("componentes")
            return

        self._results = []
        self.log.clear()
        self.progress.setValue(0)
        self._set_running(True)

        if self.tracks_check.isChecked():
            # The whole queue is one meeting, not one meeting each.
            self._queue = []
            self._append_log(f"— {len(paths)} faixas de uma reunião")
            output_dir = Path(settings.output_dir) if settings.output_dir else None
            self._start_worker(
                TrackJob(
                    sources=list(paths),
                    settings=settings,
                    output_dir=output_dir,
                    names=list(settings.speaker_names),
                )
            )
            return

        self._queue = list(paths)
        self._run_next()

    def _run_next(self) -> None:
        if not self._queue:
            self._finish_all()
            return

        source = self._queue.pop(0)
        output_dir = Path(self.settings.output_dir) if self.settings.output_dir else None
        self._append_log(f"— {source.name}")
        self._start_worker(Job(source=source, settings=self.settings, output_dir=output_dir))

    def _start_worker(self, job) -> None:
        worker = TranscriptionWorker(job)
        worker.signals.progress.connect(self._on_progress)
        worker.signals.log.connect(self._append_log)
        worker.signals.finished.connect(self._on_finished)
        worker.signals.cancelled.connect(self._on_cancelled)
        worker.signals.failed.connect(self._on_failed)
        self._worker = worker
        QtCore.QThreadPool.globalInstance().start(worker)

    def cancel(self) -> None:
        if self._worker:
            self._queue.clear()
            self.stage_label.setText("Cancelando...")
            self._worker.cancel()

    def _set_running(self, running: bool) -> None:
        self.start_btn.setEnabled(not running)
        self.cancel_btn.setEnabled(running)
        self.drop_zone.setEnabled(not running)
        if running:
            self.open_text_btn.setEnabled(False)
            self.open_folder_btn.setEnabled(False)
            self.review_btn.setEnabled(False)

    # -- worker signals ---------------------------------------------------

    @QtCore.Slot(object)
    def _on_progress(self, event: ProgressEvent) -> None:
        self.progress.setValue(event.percent)
        self.stage_label.setText(f"{event.stage}: {event.message}")
        self.detail_label.setText(event.detail)

    def _append_log(self, line: str) -> None:
        self.log.appendPlainText(line)

    @QtCore.Slot(object)
    def _on_finished(self, result: Result) -> None:
        self._worker = None
        self._results.append(result)
        transcript = result.transcript
        summary = (
            f"{len(transcript.utterances)} falas"
            + (
                f" · {transcript.speaker_count} interlocutores"
                if transcript.diarized
                else " · sem interlocutores"
            )
        )
        self._append_log(f"Pronto: {result.text_file} ({summary})")
        for note in transcript.notes:
            self._append_log(f"Atenção: {note}")
        # The Review page opens the last one transcribed, which is the one
        # somebody is going to want to check.
        self.transcript_ready.emit(transcript)
        self._run_next()

    def _on_cancelled(self) -> None:
        self._worker = None
        self._append_log("Cancelado.")
        self.stage_label.setText("Cancelado.")
        self._set_running(False)

    def _on_failed(self, message: str) -> None:
        self._worker = None
        self._notify_done()
        self._append_log(f"Falhou: {message}")
        self.stage_label.setText("Falhou.")
        self._set_running(False)
        QtWidgets.QMessageBox.warning(self, "A transcrição falhou", message)
        # A failure on one recording should not silently abandon the rest.
        if self._queue:
            self._set_running(True)
            self._run_next()

    def _notify_done(self) -> None:
        """Sound and a taskbar nudge: a two-hour run is watched by nobody.

        Deliberately not a modal: coming back to a dialog demanding a click
        before the buttons work is worse than coming back to a finished job.
        """

        if not self.settings.notify_when_done:
            return
        app = QtWidgets.QApplication.instance()
        if not app:
            return
        QtWidgets.QApplication.beep()
        window = self.window()
        if window:
            app.alert(window, 3000)

    def _finish_all(self) -> None:
        self._set_running(False)
        if not self._results:
            return
        self._notify_done()
        self.progress.setValue(100)
        self.stage_label.setText(
            "Transcrição concluída."
            if len(self._results) == 1
            else f"{len(self._results)} transcrições concluídas."
        )
        self.detail_label.setText(str(self._results[-1].text_file or ""))
        self.open_text_btn.setEnabled(True)
        self.open_folder_btn.setEnabled(True)
        self.review_btn.setEnabled(True)
        if self.settings.open_when_done:
            self._open_text()

    # -- results ----------------------------------------------------------

    def _open_text(self) -> None:
        target = self._results[-1].text_file if self._results else None
        if target:
            open_file(target)

    def _open_folder(self) -> None:
        target = self._results[-1].text_file if self._results else None
        if target:
            open_folder(target)

    def reload_settings(self) -> None:
        self.settings = load_settings()
        self._load_settings_into_form()
