"""The page the app exists for: drop a recording in, get a transcript out."""
from __future__ import annotations

from pathlib import Path

from jp2subs.gui.common import Banner, Card, Collapsible, FileQueue, ScrollPage, hline, label
from PySide6 import QtCore, QtWidgets

from ... import components
from ...config import (
    DEFAULT_PROMPT,
    Settings,
    load_settings,
    parse_speaker_names,
    save_settings,
)
from ...diarize import unavailable_reason
from ...media import is_media
from ...pipeline import Job, Result
from ...progress import ProgressEvent
from ..widgets import DropZone, browse_recordings, open_file, open_folder
from ..workers import TranscriptionWorker


class TranscribePage(ScrollPage):
    """Queue, options, progress, and the buttons that start and stop a run."""

    #: Asks the window to switch pages, e.g. to Componentes.
    navigate = QtCore.Signal(str)

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
        row.addWidget(remove)
        row.addWidget(clear)
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

        self.speakers_check = QtWidgets.QCheckBox("Identificar quem falou cada trecho")
        self.speakers_check.toggled.connect(self._on_speakers_toggled)
        form.addRow("Interlocutores", self.speakers_check)

        self.people_spin = QtWidgets.QSpinBox()
        self.people_spin.setRange(0, 50)
        self.people_spin.setSpecialValueText("Descobrir sozinho")
        self.people_spin.setSuffix(" pessoas")
        form.addRow("Quantas pessoas", self.people_spin)

        self.names_edit = QtWidgets.QLineEdit()
        self.names_edit.setPlaceholderText("Ana, João, Carla — na ordem em que falam pela primeira vez")
        form.addRow("Nomes (opcional)", self.names_edit)

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

        self.threshold_spin = QtWidgets.QDoubleSpinBox()
        self.threshold_spin.setRange(0.1, 1.5)
        self.threshold_spin.setSingleStep(0.05)
        self.threshold_spin.setToolTip(
            "Menor separa mais vozes; maior junta vozes parecidas. Só vale com "
            "'Descobrir sozinho' em Quantas pessoas."
        )
        form.addRow("Sensibilidade das vozes", self.threshold_spin)

        self.gap_spin = QtWidgets.QDoubleSpinBox()
        self.gap_spin.setRange(0.0, 10.0)
        self.gap_spin.setSingleStep(0.2)
        self.gap_spin.setSuffix(" s")
        self.gap_spin.setToolTip("Pausa máxima para juntar duas falas seguidas da mesma pessoa.")
        form.addRow("Juntar falas até", self.gap_spin)

        self.prompt_edit = QtWidgets.QPlainTextEdit()
        self.prompt_edit.setMaximumHeight(70)
        self.prompt_edit.setPlaceholderText(DEFAULT_PROMPT)
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
        for button in (self.open_text_btn, self.open_folder_btn):
            button.setEnabled(False)
            result_row.addWidget(button)
        result_row.addStretch(1)
        card.body.addLayout(result_row)

        self.content.addWidget(card)

    # -- settings <-> form ------------------------------------------------

    def _load_settings_into_form(self) -> None:
        settings = self.settings
        self.speakers_check.setChecked(settings.identify_speakers)
        self.people_spin.setValue(settings.speaker_count)
        self.names_edit.setText(", ".join(settings.speaker_names))
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
        self.threshold_spin.setValue(settings.clustering_threshold)
        self.gap_spin.setValue(settings.merge_gap)
        if settings.initial_prompt and settings.initial_prompt != DEFAULT_PROMPT:
            self.prompt_edit.setPlainText(settings.initial_prompt)
        self._on_speakers_toggled(settings.identify_speakers)

    def _collect_settings(self) -> Settings:
        settings = self.settings
        settings.model = self.model_combo.currentData() or ""
        settings.identify_speakers = self.speakers_check.isChecked()
        settings.speaker_count = self.people_spin.value()
        settings.speaker_names = parse_speaker_names(self.names_edit.text())
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
        settings.clustering_threshold = self.threshold_spin.value()
        settings.merge_gap = self.gap_spin.value()
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

    def _on_speakers_toggled(self, checked: bool) -> None:
        self.people_spin.setEnabled(checked)
        self.names_edit.setEnabled(checked)
        self.threshold_spin.setEnabled(checked)
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

        self._queue = list(paths)
        self._results = []
        self.log.clear()
        self.progress.setValue(0)
        self._set_running(True)
        self._run_next()

    def _run_next(self) -> None:
        if not self._queue:
            self._finish_all()
            return

        source = self._queue.pop(0)
        output_dir = Path(self.settings.output_dir) if self.settings.output_dir else None
        job = Job(source=source, settings=self.settings, output_dir=output_dir)

        self._append_log(f"— {source.name}")
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
        self._run_next()

    def _on_cancelled(self) -> None:
        self._worker = None
        self._append_log("Cancelado.")
        self.stage_label.setText("Cancelado.")
        self._set_running(False)

    def _on_failed(self, message: str) -> None:
        self._worker = None
        self._append_log(f"Falhou: {message}")
        self.stage_label.setText("Falhou.")
        self._set_running(False)
        QtWidgets.QMessageBox.warning(self, "A transcrição falhou", message)
        # A failure on one recording should not silently abandon the rest.
        if self._queue:
            self._set_running(True)
            self._run_next()

    def _finish_all(self) -> None:
        self._set_running(False)
        if not self._results:
            return
        self.progress.setValue(100)
        self.stage_label.setText(
            "Transcrição concluída."
            if len(self._results) == 1
            else f"{len(self._results)} transcrições concluídas."
        )
        self.detail_label.setText(str(self._results[-1].text_file or ""))
        self.open_text_btn.setEnabled(True)
        self.open_folder_btn.setEnabled(True)
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
