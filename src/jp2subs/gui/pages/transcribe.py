"""Transcribe page: the main drag-drop-run workflow."""
from __future__ import annotations

from pathlib import Path

from PySide6 import QtCore, QtWidgets

from ...paths import default_workdir_for_input
from ...runtime import store
from ...runtime.manager import manager
from .. import icons, theme
from ..common import (
    Banner,
    Card,
    Collapsible,
    DropZone,
    FileQueue,
    IconButton,
    ScrollPage,
    StageTimeline,
    browse_files,
    hline,
    label,
    reveal,
)
from ..state import PipelineJob, load_app_state, persist_app_state
from ..workers import PipelineWorker

STAGES = ("Ingest", "Transcribe", "Romanize", "Export")

DOWNLOAD_MORE = "__download_more__"


def parse_extra_args(raw: str) -> dict[str, object] | None:
    """Parse ``key=value`` pairs, separated by spaces or newlines."""

    parts = [token.strip() for token in raw.replace("\n", " ").split(" ") if token.strip()]
    payload: dict[str, object] = {}
    for token in parts:
        if "=" in token:
            key, value = token.split("=", 1)
            payload[key.strip()] = _parse_extra_value(value.strip())
    return payload or None


def _parse_extra_value(value: str) -> object:
    lowered = value.lower()
    if lowered in {"true", "yes", "on"}:
        return True
    if lowered in {"false", "no", "off"}:
        return False
    try:
        return int(value)
    except ValueError:
        pass
    try:
        return float(value)
    except ValueError:
        return value


def safe_path_component(value: str) -> str:
    cleaned = "".join(char if char.isalnum() or char in {"-", "_", "."} else "_" for char in value).strip("._")
    return cleaned or "job"


class TranscribePage(ScrollPage):
    """Queue media, pick a model, run the pipeline."""

    navigate = QtCore.Signal(str)

    def __init__(self, parent: QtWidgets.QWidget | None = None):
        super().__init__(
            "Transcribe",
            "Drop Japanese audio or video in and get subtitles out.",
            parent,
        )
        self.cfg = load_app_state()
        self.pending_jobs: list[PipelineJob] = []
        self.completed_jobs = 0
        self.total_jobs = 0
        self._worker: PipelineWorker | None = None
        self._workdir_auto = True
        self._results: list[Path] = []
        self._current_stage = ""

        self._build_readiness_banner()
        self._build_sources_card()
        self._build_options_card()
        self._build_run_row()
        self._build_progress_card()
        self._build_results_card()
        self.content.addStretch(1)

        self.refresh_components()
        self._sync_from_config()

    # -- construction -----------------------------------------------------

    def _build_readiness_banner(self) -> None:
        self.readiness = Banner("", "warning", "Open Components")
        self.readiness.action_clicked.connect(lambda: self.navigate.emit("components"))
        self.content.addWidget(self.readiness)

    def _build_sources_card(self) -> None:
        card = Card("Source files", "Drop files anywhere on this panel, or browse.", icon_name="film")

        self.dropzone = DropZone()
        self.dropzone.files_dropped.connect(self._add_sources)
        self.dropzone.browse_requested.connect(self._choose_sources)
        card.body.addWidget(self.dropzone)

        self.queue = FileQueue()
        self.queue.files_dropped.connect(self._add_sources)
        self.queue.setVisible(False)
        card.body.addWidget(self.queue)

        self.queue_actions = QtWidgets.QHBoxLayout()
        self.queue_count = label("", "Faint")
        self.queue_actions.addWidget(self.queue_count, 1)

        add_btn = IconButton("Add files", "plus")
        add_btn.clicked.connect(self._choose_sources)
        remove_btn = QtWidgets.QPushButton("Remove selected")
        remove_btn.clicked.connect(self._remove_selected)
        clear_btn = QtWidgets.QPushButton("Clear")
        clear_btn.clicked.connect(self._clear_sources)
        for button in (add_btn, remove_btn, clear_btn):
            self.queue_actions.addWidget(button, 0)

        actions_holder = QtWidgets.QWidget()
        actions_holder.setLayout(self.queue_actions)
        self.queue_actions_holder = actions_holder
        actions_holder.setVisible(False)
        card.body.addWidget(actions_holder)

        self.content.addWidget(card)

    def _build_options_card(self) -> None:
        card = Card("Transcription options", "", icon_name="sliders")

        form = QtWidgets.QFormLayout()
        form.setSpacing(11)
        form.setLabelAlignment(QtCore.Qt.AlignLeft)
        form.setFieldGrowthPolicy(QtWidgets.QFormLayout.AllNonFixedFieldsGrow)

        self.model_combo = QtWidgets.QComboBox()
        self.model_combo.setMinimumWidth(280)
        self.model_combo.activated.connect(self._on_model_activated)
        form.addRow("Model", self.model_combo)

        self.format_combo = QtWidgets.QComboBox()
        self.format_combo.addItems(["srt", "vtt", "ass"])
        form.addRow("Subtitle format", self.format_combo)

        self.romaji_check = QtWidgets.QCheckBox("Also export a romaji subtitle track")
        form.addRow("Romaji", self.romaji_check)

        workdir_row = QtWidgets.QHBoxLayout()
        workdir_row.setSpacing(8)
        self.workdir_edit = QtWidgets.QLineEdit()
        self.workdir_edit.setPlaceholderText("Automatic: a _jobs folder next to each input file")
        self.workdir_edit.textEdited.connect(self._mark_workdir_manual)
        workdir_btn = QtWidgets.QPushButton("Browse")
        workdir_btn.clicked.connect(self._choose_workdir)
        workdir_row.addWidget(self.workdir_edit, 1)
        workdir_row.addWidget(workdir_btn, 0)
        form.addRow("Output folder", workdir_row)

        card.body.addLayout(form)
        card.body.addWidget(hline())

        advanced = Collapsible("Advanced settings")

        adv_form = QtWidgets.QFormLayout()
        adv_form.setSpacing(10)
        adv_form.setFieldGrowthPolicy(QtWidgets.QFormLayout.AllNonFixedFieldsGrow)

        self.device_combo = QtWidgets.QComboBox()
        self.device_combo.addItem("Automatic (GPU when available)", "auto")
        self.device_combo.addItem("GPU (CUDA)", "cuda")
        self.device_combo.addItem("CPU", "cpu")
        adv_form.addRow("Processing device", self.device_combo)

        self.beam_spin = QtWidgets.QSpinBox()
        self.beam_spin.setRange(1, 20)
        adv_form.addRow("Beam size", self.beam_spin)

        self.vad_check = QtWidgets.QCheckBox("Skip silence before transcribing")
        adv_form.addRow("Voice detection", self.vad_check)

        self.mono_check = QtWidgets.QCheckBox("Downmix audio to mono during ingest")
        adv_form.addRow("Audio", self.mono_check)

        self.word_ts_check = QtWidgets.QCheckBox("Collect word-level timestamps")
        adv_form.addRow("Timing", self.word_ts_check)

        self.threads_spin = QtWidgets.QSpinBox()
        self.threads_spin.setRange(0, 64)
        self.threads_spin.setSpecialValueText("Automatic")
        adv_form.addRow("CPU threads", self.threads_spin)

        self.compute_combo = QtWidgets.QComboBox()
        self.compute_combo.addItems(["default", "float16", "int8", "int8_float16"])
        adv_form.addRow("Compute type", self.compute_combo)

        self.extra_args_edit = QtWidgets.QPlainTextEdit()
        self.extra_args_edit.setPlaceholderText("condition_on_previous_text=false")
        self.extra_args_edit.setMaximumHeight(70)
        adv_form.addRow("Extra ASR args", self.extra_args_edit)

        advanced.body.addLayout(adv_form)
        card.body.addWidget(advanced)

        self.content.addWidget(card)

    def _build_run_row(self) -> None:
        row = QtWidgets.QHBoxLayout()
        row.setSpacing(10)

        self.run_btn = IconButton("Start transcription", "play", primary=True)
        self.run_btn.setMinimumHeight(38)
        self.run_btn.clicked.connect(self._start)

        self.cancel_btn = IconButton("Cancel", "stop")
        self.cancel_btn.setMinimumHeight(38)
        self.cancel_btn.setEnabled(False)
        self.cancel_btn.clicked.connect(self._cancel)

        row.addWidget(self.run_btn, 0)
        row.addWidget(self.cancel_btn, 0)
        row.addStretch(1)

        holder = QtWidgets.QWidget()
        holder.setLayout(row)
        self.content.addWidget(holder)

    def _build_progress_card(self) -> None:
        self.progress_card = Card("Progress", "", icon_name="waveform")

        body = QtWidgets.QHBoxLayout()
        body.setSpacing(22)

        self.timeline = StageTimeline(STAGES)
        body.addWidget(self.timeline, 0, QtCore.Qt.AlignTop)

        right = QtWidgets.QVBoxLayout()
        right.setSpacing(8)

        self.stage_label = label("Idle", "CardTitle")
        right.addWidget(self.stage_label)

        self.progress_bar = QtWidgets.QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setTextVisible(False)
        right.addWidget(self.progress_bar)

        self.detail_label = label("", "Faint")
        right.addWidget(self.detail_label)

        self.job_label = label("", "Faint")
        right.addWidget(self.job_label)
        right.addStretch(1)

        body.addLayout(right, 1)
        self.progress_card.body.addLayout(body)

        log_section = Collapsible("Show log")
        self.log_view = QtWidgets.QTextEdit()
        self.log_view.setObjectName("LogView")
        self.log_view.setReadOnly(True)
        log_section.body.addWidget(self.log_view)
        self.progress_card.body.addWidget(log_section)

        self.progress_card.setVisible(False)
        self.content.addWidget(self.progress_card)

    def _build_results_card(self) -> None:
        self.results_card = Card("Finished files", "", icon_name="check")

        self.results_list = QtWidgets.QListWidget()
        self.results_list.itemDoubleClicked.connect(
            lambda item: reveal(item.data(QtCore.Qt.UserRole) or item.text())
        )
        self.results_card.body.addWidget(self.results_list)

        row = QtWidgets.QHBoxLayout()
        open_btn = IconButton("Open output folder", "folder")
        open_btn.clicked.connect(self._open_results_folder)
        send_btn = QtWidgets.QPushButton("Send to Finalize")
        send_btn.clicked.connect(lambda: self.navigate.emit("finalize"))
        row.addWidget(open_btn, 0)
        row.addWidget(send_btn, 0)
        row.addStretch(1)
        self.results_card.body.addLayout(row)

        self.results_card.setVisible(False)
        self.content.addWidget(self.results_card)

    # -- component awareness ----------------------------------------------

    def refresh_components(self) -> None:
        """Re-read what is installed and update the model list and banner."""

        manager.refresh()
        previous = self.model_combo.currentData()

        self.model_combo.blockSignals(True)
        self.model_combo.clear()
        installed = manager.installed_models()
        for item in installed:
            status = manager.status(item.key)
            size = store.human_size(status.size) if status else ""
            suffix = f" · {item.quality} · {item.speed}" if item.quality else ""
            self.model_combo.addItem(f"{item.name}{suffix} · {size}", item.model_alias)
        if installed:
            self.model_combo.insertSeparator(self.model_combo.count())
            self.model_combo.addItem("Download another model...", DOWNLOAD_MORE)
        else:
            self.model_combo.addItem("No model installed yet", None)
        self.model_combo.blockSignals(False)

        if previous and previous != DOWNLOAD_MORE:
            index = self.model_combo.findData(previous)
            if index >= 0:
                self.model_combo.setCurrentIndex(index)
        elif installed:
            preferred = self.model_combo.findData(manager.default_model())
            self.model_combo.setCurrentIndex(max(preferred, 0))

        self.model_combo.setEnabled(bool(installed))
        self._update_readiness()

    def _update_readiness(self) -> None:
        missing = manager.missing_required()
        if not missing:
            self.readiness.setVisible(False)
            self.run_btn.setEnabled(self._worker is None)
            return

        self.readiness.setVisible(True)
        names = ", ".join(item.name for item in missing)
        self.readiness.set_message(
            f"Before the first run you need: {names}. The app downloads and installs it for you.",
            "warning",
            "Open Components",
        )
        self.run_btn.setEnabled(False)

    def _on_model_activated(self, index: int) -> None:
        if self.model_combo.itemData(index) == DOWNLOAD_MORE:
            # Restore the previous pick so the combo never sits on the shortcut.
            for candidate in range(self.model_combo.count()):
                if self.model_combo.itemData(candidate) not in (DOWNLOAD_MORE, None):
                    self.model_combo.setCurrentIndex(candidate)
                    break
            self.navigate.emit("components")

    # -- config -----------------------------------------------------------

    def reload_config(self) -> None:
        """Re-read config.toml after the Settings page saves."""

        self._sync_from_config()

    def _sync_from_config(self) -> None:
        self.cfg = load_app_state()
        defaults = self.cfg.defaults

        index = self.format_combo.findText(defaults.subtitle_format)
        if index >= 0:
            self.format_combo.setCurrentIndex(index)
        self.beam_spin.setValue(defaults.beam_size)
        self.vad_check.setChecked(defaults.vad)
        self.mono_check.setChecked(defaults.mono)
        self.word_ts_check.setChecked(defaults.word_timestamps)
        self.threads_spin.setValue(defaults.threads or 0)
        compute_index = self.compute_combo.findText(defaults.compute_type or "default")
        if compute_index >= 0:
            self.compute_combo.setCurrentIndex(compute_index)
        self.extra_args_edit.setPlainText(
            "\n".join(f"{key}={value}" for key, value in (defaults.extra_asr_args or {}).items())
        )
        self.device_combo.setCurrentIndex(0 if self.cfg.app.prefer_gpu else 2)

        model_index = self.model_combo.findData(defaults.model_size)
        if model_index >= 0:
            self.model_combo.setCurrentIndex(model_index)

    def remember_model_choice(self) -> None:
        alias = self.model_combo.currentData()
        if not alias or alias == DOWNLOAD_MORE:
            return
        if self.cfg.defaults.model_size != alias:
            self.cfg.defaults.model_size = alias
            persist_app_state(self.cfg)

    # -- queue ------------------------------------------------------------

    def _choose_sources(self) -> None:
        self._add_sources(browse_files(self))

    def _add_sources(self, paths: list[str]) -> None:
        added = False
        for path in paths:
            if path and self.queue.add_path(str(path)):
                added = True
        if added and self._workdir_auto:
            self._update_auto_workdir()
        self._sync_queue_visibility()

    def _remove_selected(self) -> None:
        for item in self.queue.selectedItems():
            self.queue.takeItem(self.queue.row(item))
        if self._workdir_auto:
            self._update_auto_workdir()
        self._sync_queue_visibility()

    def _clear_sources(self) -> None:
        self.queue.clear()
        if self._workdir_auto:
            self.workdir_edit.clear()
        self._sync_queue_visibility()

    def _sync_queue_visibility(self) -> None:
        count = self.queue.count()
        self.queue.setVisible(bool(count))
        self.queue_actions_holder.setVisible(bool(count))
        self.dropzone.setVisible(not count)
        self.queue_count.setText(f"{count} file(s) queued" if count else "")

    def _update_auto_workdir(self) -> None:
        sources = self.queue.paths()
        if not sources:
            self.workdir_edit.clear()
        elif len(sources) == 1:
            self.workdir_edit.setText(str(default_workdir_for_input(sources[0])))
        else:
            self.workdir_edit.setText(str(sources[0].parent / "_jobs"))

    def _mark_workdir_manual(self) -> None:
        self._workdir_auto = False

    def _choose_workdir(self) -> None:
        path = QtWidgets.QFileDialog.getExistingDirectory(self, "Choose an output folder")
        if path:
            self._workdir_auto = False
            self.workdir_edit.setText(path)

    # -- run --------------------------------------------------------------

    def _build_job(self, source: Path, workdir: Path) -> PipelineJob:
        job = PipelineJob()
        job.source = source
        job.workdir = workdir
        defaults = self.cfg.defaults

        alias = self.model_combo.currentData()
        job.model_size = alias if alias and alias != DOWNLOAD_MORE else defaults.model_size
        job.beam_size = self.beam_spin.value()
        job.vad = self.vad_check.isChecked()
        job.mono = self.mono_check.isChecked()
        job.generate_romaji = self.romaji_check.isChecked()
        job.fmt = self.format_combo.currentText()
        job.device = self.device_combo.currentData() or "auto"
        job.best_of = defaults.best_of
        job.patience = defaults.patience
        job.length_penalty = defaults.length_penalty
        job.word_timestamps = self.word_ts_check.isChecked()
        job.threads = self.threads_spin.value() or defaults.threads

        compute_type = self.compute_combo.currentText()
        job.compute_type = None if compute_type == "default" else compute_type

        extra_args = dict(defaults.extra_asr_args or {})
        extra_args.update(parse_extra_args(self.extra_args_edit.toPlainText()) or {})
        extra_args["suppress_blank"] = defaults.suppress_blank
        extra_args["suppress_tokens"] = defaults.suppress_tokens
        job.extra_asr_args = extra_args
        return job

    def _resolve_workdir(self, source: Path, base: Path | None, multi: bool) -> Path:
        if not base:
            return default_workdir_for_input(source)
        if not multi:
            return base
        return base / safe_path_component(source.stem)

    def _start(self) -> None:
        sources = self.queue.paths()
        if not sources:
            QtWidgets.QMessageBox.information(
                self, "Nothing queued", "Add at least one audio or video file first."
            )
            return
        if not manager.installed_models():
            self.navigate.emit("components")
            return

        self.cfg = load_app_state()
        self.remember_model_choice()

        workdir_text = self.workdir_edit.text().strip()
        base = Path(workdir_text) if workdir_text else None
        multi = len(sources) > 1

        self.pending_jobs = [
            self._build_job(source, self._resolve_workdir(source, base, multi)) for source in sources
        ]
        self.completed_jobs = 0
        self.total_jobs = len(self.pending_jobs)
        self._results = []

        self.log_view.clear()
        self.results_list.clear()
        self.results_card.setVisible(False)
        self.progress_card.setVisible(True)
        self.timeline.reset()
        self.progress_bar.setValue(0)
        self.stage_label.setText("Preparing...")
        self.detail_label.setText("")
        self.run_btn.setEnabled(False)
        self.cancel_btn.setEnabled(True)
        self._log(f"Queued {self.total_jobs} file(s).")
        if multi and base:
            self._log("Batch mode: each file gets its own subfolder inside the output folder.")
        self._start_next()

    def _start_next(self) -> None:
        if not self.pending_jobs:
            return
        job = self.pending_jobs.pop(0)
        name = job.source.name if job.source else "Unknown"
        self.job_label.setText(f"File {self.completed_jobs + 1} of {self.total_jobs}: {name}")
        self._log(f"--- {name} ---")
        if job.workdir:
            self._log(f"Output: {job.workdir}")
        self.timeline.reset()
        self.progress_bar.setValue(0)

        worker = PipelineWorker(job)
        self._worker = worker
        worker.signals.log.connect(self._log)
        worker.signals.failed.connect(self._on_failed)
        worker.signals.cancelled.connect(self._on_cancelled)
        worker.signals.results.connect(self._on_results)
        worker.signals.finished.connect(self._on_finished)
        worker.signals.progress.connect(self.progress_bar.setValue)
        worker.signals.stage.connect(self.stage_label.setText)
        worker.signals.detail.connect(self.detail_label.setText)
        worker.signals.stage_started.connect(self._on_stage_started)
        worker.signals.stage_done.connect(lambda stage: self.timeline.set_state(stage, "done"))
        QtCore.QThreadPool.globalInstance().start(worker)

    def _on_stage_started(self, stage: str) -> None:
        self._current_stage = stage
        self.timeline.set_state(stage, "active")

    def _cancel(self) -> None:
        if self._worker:
            self._worker.cancel()
        self.pending_jobs = []
        self._log("Cancelling...")

    def _log(self, line: str) -> None:
        self.log_view.append(line)

    @QtCore.Slot(list)
    def _on_results(self, items: list) -> None:
        for item in items:
            path = Path(item)
            self._results.append(path)
            entry = QtWidgets.QListWidgetItem(path.name)
            entry.setData(QtCore.Qt.UserRole, str(path))
            entry.setToolTip(str(path))
            entry.setIcon(icons.icon("check", 15, theme.active_palette().success))
            self.results_list.addItem(entry)
        self.results_card.setVisible(bool(self._results))

    def _on_finished(self) -> None:
        self.completed_jobs += 1
        if self.pending_jobs:
            self._start_next()
            return
        self._worker = None
        self.progress_bar.setValue(100)
        self.stage_label.setText("All done")
        self.detail_label.setText(f"{len(self._results)} file(s) written")
        self.job_label.setText("")
        self._log("Finished.")
        self._reset_controls()
        if self.cfg.app.open_output_when_done and self._results:
            reveal(self._results[0])

    def _on_failed(self, message: str) -> None:
        self._worker = None
        self.pending_jobs = []
        self.stage_label.setText("Failed")
        self.detail_label.setText(message)
        if self._current_stage:
            self.timeline.set_state(self._current_stage, "failed")
        self._log(f"Error: {message}")
        self._reset_controls()
        QtWidgets.QMessageBox.critical(self, "Transcription failed", message)

    def _on_cancelled(self) -> None:
        self._worker = None
        self.pending_jobs = []
        self.stage_label.setText("Cancelled")
        self.detail_label.setText("")
        self._log("Cancelled.")
        self._reset_controls()

    def _reset_controls(self) -> None:
        self.cancel_btn.setEnabled(False)
        self._update_readiness()

    def _open_results_folder(self) -> None:
        if self._results:
            reveal(self._results[0])
        elif self.workdir_edit.text().strip():
            reveal(Path(self.workdir_edit.text().strip()))
