"""Qt widgets for jp2subs GUI."""
from __future__ import annotations

from pathlib import Path
from typing import List

from ..paths import default_workdir_for_input
from .state import FinalizeJob, PipelineJob, load_app_state, persist_app_state
from .worker import FinalizeWorker, PipelineWorker

try:  # pragma: no cover - optional dependency
    from PySide6 import QtCore, QtGui, QtWidgets
except Exception:  # pragma: no cover - allow import without Qt
    QtCore = QtGui = QtWidgets = None  # type: ignore


def parse_extra_args(raw: str) -> dict[str, str] | None:
    """Parse key=value pairs into a mapping."""

    parts = [token.strip() for token in raw.replace("\n", " ").split(" ") if token.strip()]
    payload: dict[str, str] = {}
    for token in parts:
        if "=" in token:
            key, value = token.split("=", 1)
            payload[key.strip()] = value.strip()
    return payload or None


class BaseWidget(QtWidgets.QWidget if QtWidgets else object):  # type: ignore[misc]
    def __init__(self, *args, **kwargs):
        if not QtWidgets:
            raise RuntimeError("PySide6 is required for the GUI")
        super().__init__(*args, **kwargs)


class PipelineTab(BaseWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.cfg = load_app_state()
        self.job = PipelineJob()
        self.thread_pool = QtCore.QThreadPool.globalInstance() if QtCore else None
        self.pending_jobs: list[PipelineJob] = []
        self.completed_jobs = 0
        self.total_jobs = 0
        self._setup_ui()

    def _setup_ui(self):
        layout = QtWidgets.QVBoxLayout(self)

        body = QtWidgets.QHBoxLayout()
        self.stage_list = StageListWidget()
        body.addWidget(self.stage_list, 1)

        main_area = QtWidgets.QVBoxLayout()
        defaults_hint = QtWidgets.QLabel(
            "Job options respect your global defaults from the Settings tab. "
            "Use the button below to re-apply them at any time."
        )
        defaults_hint.setWordWrap(True)

        defaults_row = QtWidgets.QHBoxLayout()
        defaults_row.addWidget(defaults_hint)
        self.defaults_btn = QtWidgets.QPushButton("Load defaults from Settings")
        self.defaults_btn.clicked.connect(self._sync_from_cfg)
        defaults_row.addStretch(1)
        defaults_row.addWidget(self.defaults_btn)

        file_row = QtWidgets.QHBoxLayout()
        self.source_list = QtWidgets.QListWidget()
        self.source_list.setSelectionMode(QtWidgets.QAbstractItemView.ExtendedSelection)
        pick_btn = QtWidgets.QPushButton("Choose files")
        pick_btn.clicked.connect(self._choose_source)
        remove_btn = QtWidgets.QPushButton("Remove selected")
        remove_btn.clicked.connect(self._remove_selected_sources)
        clear_btn = QtWidgets.QPushButton("Clear queue")
        clear_btn.clicked.connect(self._clear_sources)
        file_btns = QtWidgets.QVBoxLayout()
        file_btns.addWidget(pick_btn)
        file_btns.addWidget(remove_btn)
        file_btns.addWidget(clear_btn)
        file_row.addWidget(self.source_list)
        file_row.addLayout(file_btns)

        workdir_row = QtWidgets.QHBoxLayout()
        self.workdir_edit = QtWidgets.QLineEdit()
        workdir_btn = QtWidgets.QPushButton("Workdir folder")
        workdir_btn.clicked.connect(self._choose_workdir)
        workdir_row.addWidget(self.workdir_edit)
        workdir_row.addWidget(workdir_btn)

        self.defaults_summary = QtWidgets.QLabel("")
        self.defaults_summary.setWordWrap(True)
        self.romaji_check = QtWidgets.QCheckBox("Generate romaji")
        options_box = QtWidgets.QGroupBox("Job options")
        options_layout = QtWidgets.QVBoxLayout()
        options_layout.addWidget(self.romaji_check)
        advanced_notice = QtWidgets.QLabel(
            "ASR settings come from the Settings tab. Update them there to change defaults."
        )
        advanced_notice.setWordWrap(True)
        options_layout.addWidget(advanced_notice)
        options_box.setLayout(options_layout)

        self.progress_bar = QtWidgets.QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.stage_label = QtWidgets.QLabel("Idle")
        self.detail_label = QtWidgets.QLabel("")

        progress_box = QtWidgets.QVBoxLayout()
        progress_box.addWidget(self.progress_bar)
        progress_box.addWidget(QtWidgets.QLabel("Current stage"))
        progress_box.addWidget(self.stage_label)
        progress_box.addWidget(QtWidgets.QLabel("Detail"))
        progress_box.addWidget(self.detail_label)

        self.log_view = QtWidgets.QTextEdit()
        self.log_view.setReadOnly(True)
        self.results_list = QtWidgets.QListWidget()
        self.run_btn = QtWidgets.QPushButton("Run")
        self.run_btn.clicked.connect(self._start_job)
        self.cancel_btn = QtWidgets.QPushButton("Cancel queue")
        self.cancel_btn.setEnabled(False)
        self.cancel_btn.clicked.connect(self._cancel_job)

        main_area.addLayout(defaults_row)
        main_area.addWidget(self.defaults_summary)
        main_area.addLayout(file_row)
        main_area.addLayout(workdir_row)
        main_area.addWidget(options_box)
        main_area.addLayout(progress_box)
        btn_row = QtWidgets.QHBoxLayout()
        btn_row.addWidget(self.run_btn)
        btn_row.addWidget(self.cancel_btn)
        main_area.addLayout(btn_row)
        main_area.addWidget(QtWidgets.QLabel("Log"))
        main_area.addWidget(self.log_view)
        main_area.addWidget(QtWidgets.QLabel("Generated files"))
        main_area.addWidget(self.results_list)
        body.addLayout(main_area, 4)
        layout.addLayout(body)
        self._sync_from_cfg()

    def _choose_workdir(self):  # pragma: no cover - GUI
        path = QtWidgets.QFileDialog.getExistingDirectory(self, "Workdir")
        if path:
            self.workdir_edit.setText(path)

    def _start_job(self):  # pragma: no cover - GUI
        sources = [Path(self.source_list.item(i).text()) for i in range(self.source_list.count())]
        if not sources:
            self.log_view.append("No sources selected")
            return

        workdir_text = self.workdir_edit.text()
        workdir = Path(workdir_text) if workdir_text else None

        self.pending_jobs: list[PipelineJob] = [self._build_job(source, workdir) for source in sources]
        self.completed_jobs = 0
        self.total_jobs = len(self.pending_jobs)

        self.log_view.append(f"Queued {self.total_jobs} job(s). Starting...")
        self.progress_bar.setValue(0)
        self.stage_label.setText("Preparing...")
        self.detail_label.setText("")
        self.run_btn.setEnabled(False)
        self.cancel_btn.setEnabled(True)
        self.results_list.clear()
        self._reset_stage_list()
        self._start_next_job()

    def _on_failed(self, msg: str):  # pragma: no cover - GUI
        self.log_view.append(f"Error: {msg}")
        self.pending_jobs = []
        self._finalize_controls()

    def _on_finished(self):  # pragma: no cover - GUI
        self.completed_jobs += 1
        if self.pending_jobs:
            self._start_next_job()
        else:
            self.progress_bar.setValue(100)
            self.stage_label.setText("Complete")
            self.log_view.append("All jobs complete")
            self._finalize_controls()

    def _finalize_controls(self):  # pragma: no cover - GUI
        self.run_btn.setEnabled(True)
        self.cancel_btn.setEnabled(False)

    def _cancel_job(self):  # pragma: no cover - GUI
        if hasattr(self, "_worker"):
            self._worker.cancel()
        self.pending_jobs = []
        self.log_view.append("Cancelling queue...")

    def _populate_results(self, items: List[Path]):  # pragma: no cover - GUI
        for item in items:
            self.results_list.addItem(str(item))

    def _choose_source(self):  # pragma: no cover - GUI
        paths, _ = QtWidgets.QFileDialog.getOpenFileNames(self, "Choose files")
        for path in paths:
            if not any(self.source_list.item(i).text() == path for i in range(self.source_list.count())):
                self.source_list.addItem(path)
        if paths and not self.workdir_edit.text():
            suggestion = default_workdir_for_input(Path(paths[0]))
            self.workdir_edit.setText(str(suggestion))

    def _remove_selected_sources(self):  # pragma: no cover - GUI
        for item in self.source_list.selectedItems():
            self.source_list.takeItem(self.source_list.row(item))

    def _clear_sources(self):  # pragma: no cover - GUI
        self.source_list.clear()

    def _start_next_job(self):  # pragma: no cover - GUI
        if not self.pending_jobs:
            return
        job = self.pending_jobs.pop(0)
        self.log_view.append(
            f"Starting job {self.completed_jobs + 1}/{self.total_jobs}: {job.source.name if job.source else 'Unknown'}"
        )
        self.progress_bar.setValue(0)
        self.stage_label.setText("Preparing...")
        self.detail_label.setText("")
        worker = PipelineWorker(job)
        self._worker = worker
        worker.signals.log.connect(self.log_view.append)
        worker.signals.failed.connect(self._on_failed)
        worker.signals.results.connect(self._populate_results)
        worker.signals.finished.connect(self._on_finished)
        worker.signals.progress.connect(self.progress_bar.setValue)
        worker.signals.stage.connect(self.stage_label.setText)
        worker.signals.detail.connect(self.detail_label.setText)
        worker.signals.stage_started.connect(self._on_stage_started)
        worker.signals.stage_done.connect(self._on_stage_done)
        if self.thread_pool:
            self.thread_pool.start(worker)

    def _build_job(self, source: Path, workdir: Path | None) -> PipelineJob:
        job = PipelineJob()
        job.source = source
        job.workdir = workdir or default_workdir_for_input(source)
        self.cfg = load_app_state()
        defaults = self.cfg.defaults
        job.model_size = defaults.model_size
        job.beam_size = defaults.beam_size
        job.vad = defaults.vad
        job.mono = defaults.mono
        job.generate_romaji = self.romaji_check.isChecked()
        job.fmt = defaults.subtitle_format
        job.best_of = defaults.best_of
        job.patience = defaults.patience
        job.length_penalty = defaults.length_penalty
        job.word_timestamps = defaults.word_timestamps
        job.threads = defaults.threads
        job.compute_type = defaults.compute_type
        job.extra_asr_args = defaults.extra_asr_args
        return job

    def _reset_stage_list(self):  # pragma: no cover - GUI
        for i in range(self.stage_list.count()):
            item = self.stage_list.item(i)
            base = item.text().replace("✓ ", "")
            item.setText(base)
            font = item.font()
            font.setBold(False)
            item.setFont(font)
            item.setBackground(QtGui.QBrush())

    def _on_stage_started(self, name: str):  # pragma: no cover - GUI
        self.stage_list.highlight(name)

    def _on_stage_done(self, name: str):  # pragma: no cover - GUI
        self.stage_list.mark_done(name)

    def _sync_from_cfg(self):
        """Mirror saved defaults into the pipeline form."""
        self.cfg = load_app_state()
        defaults = self.cfg.defaults
        summary = [
            f"Model: {defaults.model_size}",
            f"Beam size: {defaults.beam_size}",
            f"VAD: {'on' if defaults.vad else 'off'}",
            f"Mono: {'on' if defaults.mono else 'off'}",
            f"Subtitle format: {defaults.subtitle_format}",
        ]
        advanced = []
        if defaults.best_of is not None:
            advanced.append(f"Best of: {defaults.best_of if defaults.best_of > 0 else 'auto'}")
        if defaults.patience is not None:
            advanced.append(f"Patience: {defaults.patience}")
        if defaults.length_penalty is not None:
            advanced.append(f"Length penalty: {defaults.length_penalty}")
        advanced.append(f"Word timestamps: {'on' if defaults.word_timestamps else 'off'}")
        if defaults.threads:
            advanced.append(f"Threads: {defaults.threads}")
        if defaults.compute_type:
            advanced.append(f"Compute: {defaults.compute_type}")
        if defaults.extra_asr_args:
            formatted = ", ".join(f"{k}={v}" for k, v in defaults.extra_asr_args.items())
            advanced.append(f"Extra args: {formatted}")

        summary_text = "Using Settings defaults: " + " • ".join(summary + advanced)
        self.defaults_summary.setText(summary_text)
        self.romaji_check.setChecked(False)


class FinalizeTab(BaseWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.thread_pool = QtCore.QThreadPool.globalInstance() if QtCore else None
        self._setup_ui()

    def _setup_ui(self):
        layout = QtWidgets.QVBoxLayout(self)
        self.video_edit = QtWidgets.QLineEdit()
        self.subs_edit = QtWidgets.QLineEdit()

        video_btn = QtWidgets.QPushButton("Choose video")
        video_btn.clicked.connect(self._choose_video)
        subs_btn = QtWidgets.QPushButton("Choose subtitle")
        subs_btn.clicked.connect(self._choose_subs)

        video_row = QtWidgets.QHBoxLayout()
        video_row.addWidget(self.video_edit)
        video_row.addWidget(video_btn)

        subs_row = QtWidgets.QHBoxLayout()
        subs_row.addWidget(self.subs_edit)
        subs_row.addWidget(subs_btn)

        self.mode_combo = QtWidgets.QComboBox()
        self.mode_combo.addItems(["sidecar", "softcode", "hardcode"])
        self.codec_edit = QtWidgets.QLineEdit("libx264")
        self.crf_spin = QtWidgets.QSpinBox()
        self.crf_spin.setRange(10, 40)
        self.crf_spin.setValue(18)

        form = QtWidgets.QFormLayout()
        form.addRow("Mode", self.mode_combo)
        form.addRow("Codec", self.codec_edit)
        form.addRow("CRF", self.crf_spin)

        self.run_btn = QtWidgets.QPushButton("Run")
        self.run_btn.clicked.connect(self._start_job)
        self.log_view = QtWidgets.QTextEdit()
        self.log_view.setReadOnly(True)

        layout.addLayout(video_row)
        layout.addLayout(subs_row)
        layout.addLayout(form)
        layout.addWidget(self.run_btn)
        layout.addWidget(self.log_view)

    def _choose_video(self):  # pragma: no cover - GUI
        path, _ = QtWidgets.QFileDialog.getOpenFileName(self, "Video")
        if path:
            self.video_edit.setText(path)

    def _choose_subs(self):  # pragma: no cover - GUI
        path, _ = QtWidgets.QFileDialog.getOpenFileName(self, "Subtitles")
        if path:
            self.subs_edit.setText(path)

    def _start_job(self):  # pragma: no cover - GUI
        job = FinalizeJob()
        job.video = Path(self.video_edit.text()) if self.video_edit.text() else None
        job.subtitle = Path(self.subs_edit.text()) if self.subs_edit.text() else None
        job.mode = self.mode_combo.currentText()
        job.codec = self.codec_edit.text() or "libx264"
        job.crf = self.crf_spin.value()

        worker = FinalizeWorker(job)
        worker.signals.log.connect(self.log_view.append)
        worker.signals.failed.connect(lambda msg: self.log_view.append(f"Error: {msg}"))
        worker.signals.results.connect(lambda items: self.log_view.append(f"Output: {items[0]}"))
        if self.thread_pool:
            self.thread_pool.start(worker)


class SettingsTab(BaseWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.cfg = load_app_state()
        layout = QtWidgets.QVBoxLayout(self)
        form = QtWidgets.QFormLayout()

        self.ffmpeg_edit = QtWidgets.QLineEdit(self.cfg.ffmpeg_path or "")
        ffmpeg_btn = QtWidgets.QPushButton("Browse")
        ffmpeg_btn.clicked.connect(self._choose_ffmpeg)
        ffmpeg_row = QtWidgets.QHBoxLayout()
        ffmpeg_row.addWidget(self.ffmpeg_edit)
        ffmpeg_row.addWidget(ffmpeg_btn)
        form.addRow("ffmpeg path", ffmpeg_row)

        self.model_size_edit = QtWidgets.QLineEdit(self.cfg.defaults.model_size)
        self.beam_size_spin = QtWidgets.QSpinBox()
        self.beam_size_spin.setRange(1, 10)
        self.beam_size_spin.setValue(self.cfg.defaults.beam_size)
        self.vad_check = QtWidgets.QCheckBox()
        self.vad_check.setChecked(self.cfg.defaults.vad)
        self.mono_check = QtWidgets.QCheckBox()
        self.mono_check.setChecked(self.cfg.defaults.mono)
        self.subtitle_fmt_combo = QtWidgets.QComboBox()
        self.subtitle_fmt_combo.addItems(["srt", "vtt", "ass"])
        idx = self.subtitle_fmt_combo.findText(self.cfg.defaults.subtitle_format)
        if idx >= 0:
            self.subtitle_fmt_combo.setCurrentIndex(idx)

        self.best_of_spin = QtWidgets.QSpinBox()
        self.best_of_spin.setRange(0, 10)
        self.best_of_spin.setValue(self.cfg.defaults.best_of or 0)
        self.patience_spin = QtWidgets.QDoubleSpinBox()
        self.patience_spin.setRange(0.0, 10.0)
        self.patience_spin.setDecimals(2)
        self.patience_spin.setValue(self.cfg.defaults.patience or 0.0)
        self.length_penalty_spin = QtWidgets.QDoubleSpinBox()
        self.length_penalty_spin.setRange(-5.0, 5.0)
        self.length_penalty_spin.setDecimals(2)
        self.length_penalty_spin.setValue(self.cfg.defaults.length_penalty or 0.0)
        self.word_ts_check = QtWidgets.QCheckBox()
        self.word_ts_check.setChecked(self.cfg.defaults.word_timestamps)
        self.thread_spin = QtWidgets.QSpinBox()
        self.thread_spin.setRange(0, 64)
        self.thread_spin.setValue(self.cfg.defaults.threads or 0)
        self.compute_combo = QtWidgets.QComboBox()
        self.compute_combo.addItems(["default", "float16", "int8", "int8_float16"])
        compute_idx = self.compute_combo.findText(self.cfg.defaults.compute_type or "default")
        if compute_idx >= 0:
            self.compute_combo.setCurrentIndex(compute_idx)
        self.extra_args_edit = QtWidgets.QPlainTextEdit()
        self.extra_args_edit.setPlaceholderText("key=value pairs, one line or space separated")
        self.extra_args_edit.setPlainText(self._format_extra_args(self.cfg.defaults.extra_asr_args))

        form.addRow("Model size", self.model_size_edit)
        form.addRow("Beam size", self.beam_size_spin)
        form.addRow("VAD", self.vad_check)
        form.addRow("Force mono", self.mono_check)
        form.addRow("Subtitle format", self.subtitle_fmt_combo)
        translation_notice = QtWidgets.QLabel(
            "Translation settings were removed. Use an external service like DeepL, ChatGPT, or a local LLM to translate transcripts."
        )
        translation_notice.setWordWrap(True)
        form.addRow("Translation", translation_notice)
        advanced_box = QtWidgets.QGroupBox("Advanced ASR")
        advanced_form = QtWidgets.QFormLayout()
        advanced_form.addRow("Best of (0=auto)", self.best_of_spin)
        advanced_form.addRow("Patience", self.patience_spin)
        advanced_form.addRow("Length penalty", self.length_penalty_spin)
        advanced_form.addRow("Word timestamps", self.word_ts_check)
        advanced_form.addRow("Threads (0=auto)", self.thread_spin)
        advanced_form.addRow("Compute type", self.compute_combo)
        advanced_form.addRow("Extra ASR args", self.extra_args_edit)
        advanced_box.setLayout(advanced_form)
        form.addRow(advanced_box)
        defaults_help = QtWidgets.QLabel(
            "These values set the defaults applied to new pipeline jobs."
        )
        defaults_help.setStyleSheet("color: #555;")
        form.addRow("Defaults", defaults_help)

        btn_row = QtWidgets.QHBoxLayout()
        save_btn = QtWidgets.QPushButton("Save")
        save_btn.clicked.connect(self._save)
        reload_btn = QtWidgets.QPushButton("Load")
        reload_btn.clicked.connect(self._load)
        reset_btn = QtWidgets.QPushButton("Reset to defaults")
        reset_btn.clicked.connect(self._reset)
        detect_btn = QtWidgets.QPushButton("Detect ffmpeg")
        detect_btn.clicked.connect(self._detect_ffmpeg)
        btn_row.addWidget(save_btn)
        btn_row.addWidget(reload_btn)
        btn_row.addWidget(reset_btn)
        btn_row.addWidget(detect_btn)

        layout.addLayout(form)
        layout.addLayout(btn_row)
        layout.addStretch(1)

    def _choose_ffmpeg(self):  # pragma: no cover - GUI
        path, _ = QtWidgets.QFileDialog.getOpenFileName(self, "Select ffmpeg")
        if path:
            self.ffmpeg_edit.setText(path)

    def _save(self):
        self.cfg.ffmpeg_path = self.ffmpeg_edit.text() or None
        self.cfg.defaults.model_size = self.model_size_edit.text() or "large-v3"
        self.cfg.defaults.beam_size = self.beam_size_spin.value()
        self.cfg.defaults.vad = self.vad_check.isChecked()
        self.cfg.defaults.mono = self.mono_check.isChecked()
        self.cfg.defaults.subtitle_format = self.subtitle_fmt_combo.currentText()
        self.cfg.defaults.best_of = self.best_of_spin.value() or None
        self.cfg.defaults.patience = self.patience_spin.value() or None
        self.cfg.defaults.length_penalty = self.length_penalty_spin.value() or None
        self.cfg.defaults.word_timestamps = self.word_ts_check.isChecked()
        self.cfg.defaults.threads = self.thread_spin.value() or None
        compute_type = self.compute_combo.currentText()
        self.cfg.defaults.compute_type = None if compute_type == "default" else compute_type
        self.cfg.defaults.extra_asr_args = parse_extra_args(self.extra_args_edit.toPlainText())
        persist_app_state(self.cfg)

    def _load(self):
        self.cfg = load_app_state()
        self._sync_from_cfg()

    def _reset(self):
        self.cfg = type(self.cfg)()
        self._sync_from_cfg()

    def _detect_ffmpeg(self):
        from ..config import detect_ffmpeg

        detected = detect_ffmpeg(self.ffmpeg_edit.text() or None)
        if detected:
            self.ffmpeg_edit.setText(detected)

    def _sync_from_cfg(self):
        self.ffmpeg_edit.setText(self.cfg.ffmpeg_path or "")
        self.model_size_edit.setText(self.cfg.defaults.model_size)
        self.beam_size_spin.setValue(self.cfg.defaults.beam_size)
        self.vad_check.setChecked(self.cfg.defaults.vad)
        self.mono_check.setChecked(self.cfg.defaults.mono)
        idx = self.subtitle_fmt_combo.findText(self.cfg.defaults.subtitle_format)
        if idx >= 0:
            self.subtitle_fmt_combo.setCurrentIndex(idx)
        self.best_of_spin.setValue(self.cfg.defaults.best_of or 0)
        self.patience_spin.setValue(self.cfg.defaults.patience or 0.0)
        self.length_penalty_spin.setValue(self.cfg.defaults.length_penalty or 0.0)
        self.word_ts_check.setChecked(self.cfg.defaults.word_timestamps)
        self.thread_spin.setValue(self.cfg.defaults.threads or 0)
        compute_idx = self.compute_combo.findText(self.cfg.defaults.compute_type or "default")
        if compute_idx >= 0:
            self.compute_combo.setCurrentIndex(compute_idx)
        self.extra_args_edit.setPlainText(self._format_extra_args(self.cfg.defaults.extra_asr_args))

    def _format_extra_args(self, extra_args: dict[str, str] | None) -> str:
        if not extra_args:
            return ""
        return "\n".join(f"{key}={value}" for key, value in extra_args.items())


class MainWindow(QtWidgets.QMainWindow if QtWidgets else object):  # type: ignore[misc]
    def __init__(self):
        if not QtWidgets:
            raise RuntimeError("PySide6 is required for the GUI")
        super().__init__()
        self.setWindowTitle("jp2subs")
        tabs = QtWidgets.QTabWidget()
        tabs.addTab(PipelineTab(), "Pipeline")
        tabs.addTab(FinalizeTab(), "Finalize")
        tabs.addTab(SettingsTab(), "Settings")
        self.setCentralWidget(tabs)


STAGES = [
    "Ingest",
    "Transcribe",
    "Romanize",
    "Export",
    "Finalize",
]


class StageListWidget(QtWidgets.QListWidget if QtWidgets else object):  # type: ignore[misc]
    def __init__(self, parent=None):
        super().__init__(parent)
        if not QtWidgets:
            return
        self.setSelectionMode(QtWidgets.QAbstractItemView.NoSelection)
        for stage in STAGES:
            self.addItem(stage)

    def highlight(self, stage: str):  # pragma: no cover - GUI
        for i in range(self.count()):
            item = self.item(i)
            base = item.text().replace("✓ ", "")
            item.setText(base)
            font = item.font()
            font.setBold(False)
            item.setFont(font)
            item.setBackground(QtGui.QBrush())
        matches = self.findItems(stage, QtCore.Qt.MatchStartsWith)
        if matches:
            item = matches[0]
            font = item.font()
            font.setBold(True)
            item.setFont(font)
            item.setBackground(QtGui.QColor("#cfe3ff"))

    def mark_done(self, stage: str):  # pragma: no cover - GUI
        matches = self.findItems(stage, QtCore.Qt.MatchStartsWith)
        if matches:
            item = matches[0]
            base = item.text().replace("✓ ", "")
            item.setText(f"✓ {base}")
