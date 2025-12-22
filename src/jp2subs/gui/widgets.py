"""Qt widgets for jp2subs GUI."""
from __future__ import annotations

from pathlib import Path
from typing import List

from ..paths import default_workdir_for_input
from .state import FinalizeJob, PipelineJob
from .worker import FinalizeWorker, PipelineWorker

try:  # pragma: no cover - optional dependency
    from PySide6 import QtCore, QtGui, QtWidgets
except Exception:  # pragma: no cover - allow import without Qt
    QtCore = QtGui = QtWidgets = None  # type: ignore


class BaseWidget(QtWidgets.QWidget if QtWidgets else object):  # type: ignore[misc]
    def __init__(self, *args, **kwargs):
        if not QtWidgets:
            raise RuntimeError("PySide6 is required for the GUI")
        super().__init__(*args, **kwargs)


class PipelineTab(BaseWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.job = PipelineJob()
        self.thread_pool = QtCore.QThreadPool.globalInstance() if QtCore else None
        self.pending_jobs: list[PipelineJob] = []
        self.completed_jobs = 0
        self.total_jobs = 0
        self._setup_ui()

    def _setup_ui(self):
        layout = QtWidgets.QVBoxLayout(self)

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

        options_row = QtWidgets.QHBoxLayout()
        self.model_input = QtWidgets.QLineEdit("large-v3")
        self.beam_slider = QtWidgets.QSlider(QtCore.Qt.Horizontal)
        self.beam_slider.setRange(1, 10)
        self.beam_slider.setValue(5)
        self.vad_check = QtWidgets.QCheckBox("VAD")
        self.vad_check.setChecked(True)
        self.mono_check = QtWidgets.QCheckBox("Mono")
        options_row.addWidget(QtWidgets.QLabel("Model"))
        options_row.addWidget(self.model_input)
        options_row.addWidget(QtWidgets.QLabel("Beam"))
        options_row.addWidget(self.beam_slider)
        options_row.addWidget(self.vad_check)
        options_row.addWidget(self.mono_check)

        translation_row = QtWidgets.QHBoxLayout()
        self.lang_edit = QtWidgets.QLineEdit("en")
        self.bilingual_edit = QtWidgets.QLineEdit()
        self.romaji_check = QtWidgets.QCheckBox("Generate romaji")
        translation_row.addWidget(QtWidgets.QLabel("Languages (comma-separated, blank = Japanese only)"))
        translation_row.addWidget(self.lang_edit)
        translation_row.addWidget(QtWidgets.QLabel("Bilingual"))
        translation_row.addWidget(self.bilingual_edit)
        translation_row.addWidget(self.romaji_check)

        fmt_row = QtWidgets.QHBoxLayout()
        self.fmt_combo = QtWidgets.QComboBox()
        self.fmt_combo.addItems(["srt", "vtt", "ass"])
        fmt_row.addWidget(QtWidgets.QLabel("Format"))
        fmt_row.addWidget(self.fmt_combo)

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
        self.cancel_btn = QtWidgets.QPushButton("Cancel")
        self.cancel_btn.setEnabled(False)
        self.cancel_btn.clicked.connect(self._cancel_job)

        layout.addLayout(file_row)
        layout.addLayout(workdir_row)
        layout.addLayout(options_row)
        layout.addLayout(translation_row)
        layout.addLayout(fmt_row)
        layout.addLayout(progress_box)
        btn_row = QtWidgets.QHBoxLayout()
        btn_row.addWidget(self.run_btn)
        btn_row.addWidget(self.cancel_btn)
        layout.addLayout(btn_row)
        layout.addWidget(QtWidgets.QLabel("Log"))
        layout.addWidget(self.log_view)
        layout.addWidget(QtWidgets.QLabel("Generated files"))
        layout.addWidget(self.results_list)

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
        if self.thread_pool:
            self.thread_pool.start(worker)

    def _build_job(self, source: Path, workdir: Path | None) -> PipelineJob:
        job = PipelineJob()
        job.source = source
        job.workdir = workdir or default_workdir_for_input(source)
        job.model_size = self.model_input.text() or "large-v3"
        job.beam_size = self.beam_slider.value()
        job.vad = self.vad_check.isChecked()
        job.mono = self.mono_check.isChecked()
        job.generate_romaji = self.romaji_check.isChecked()
        job.languages = [lang.strip() for lang in self.lang_edit.text().split(",") if lang.strip()]
        job.bilingual = self.bilingual_edit.text() or None
        job.fmt = self.fmt_combo.currentText()
        return job


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
        layout = QtWidgets.QVBoxLayout(self)
        layout.addWidget(
            QtWidgets.QLabel(
                "Configure paths and defaults in the config.toml file located at %APPDATA%/jp2subs."
            )
        )


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

