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
            raise RuntimeError("PySide6 é necessário para a GUI")
        super().__init__(*args, **kwargs)


class PipelineTab(BaseWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.job = PipelineJob()
        self.thread_pool = QtCore.QThreadPool.globalInstance() if QtCore else None
        self._setup_ui()

    def _setup_ui(self):
        layout = QtWidgets.QVBoxLayout(self)

        file_row = QtWidgets.QHBoxLayout()
        self.source_edit = QtWidgets.QLineEdit()
        pick_btn = QtWidgets.QPushButton("Escolher arquivo")
        pick_btn.clicked.connect(self._choose_source)
        file_row.addWidget(self.source_edit)
        file_row.addWidget(pick_btn)

        workdir_row = QtWidgets.QHBoxLayout()
        self.workdir_edit = QtWidgets.QLineEdit()
        workdir_btn = QtWidgets.QPushButton("Pasta workdir")
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
        options_row.addWidget(QtWidgets.QLabel("Modelo"))
        options_row.addWidget(self.model_input)
        options_row.addWidget(QtWidgets.QLabel("Beam"))
        options_row.addWidget(self.beam_slider)
        options_row.addWidget(self.vad_check)
        options_row.addWidget(self.mono_check)

        translation_row = QtWidgets.QHBoxLayout()
        self.lang_edit = QtWidgets.QLineEdit("pt-BR")
        self.bilingual_edit = QtWidgets.QLineEdit()
        self.romaji_check = QtWidgets.QCheckBox("Gerar romaji")
        translation_row.addWidget(QtWidgets.QLabel("Idiomas (vírgula)"))
        translation_row.addWidget(self.lang_edit)
        translation_row.addWidget(QtWidgets.QLabel("Bilingue"))
        translation_row.addWidget(self.bilingual_edit)
        translation_row.addWidget(self.romaji_check)

        fmt_row = QtWidgets.QHBoxLayout()
        self.fmt_combo = QtWidgets.QComboBox()
        self.fmt_combo.addItems(["srt", "vtt", "ass"])
        fmt_row.addWidget(QtWidgets.QLabel("Formato"))
        fmt_row.addWidget(self.fmt_combo)

        self.log_view = QtWidgets.QTextEdit()
        self.log_view.setReadOnly(True)
        self.results_list = QtWidgets.QListWidget()
        self.run_btn = QtWidgets.QPushButton("Run")
        self.run_btn.clicked.connect(self._start_job)

        layout.addLayout(file_row)
        layout.addLayout(workdir_row)
        layout.addLayout(options_row)
        layout.addLayout(translation_row)
        layout.addLayout(fmt_row)
        layout.addWidget(self.run_btn)
        layout.addWidget(QtWidgets.QLabel("Log"))
        layout.addWidget(self.log_view)
        layout.addWidget(QtWidgets.QLabel("Arquivos gerados"))
        layout.addWidget(self.results_list)

    def _choose_source(self):  # pragma: no cover - GUI
        path, _ = QtWidgets.QFileDialog.getOpenFileName(self, "Escolher arquivo")
        if path:
            self.source_edit.setText(path)
            suggestion = default_workdir_for_input(Path(path))
            self.workdir_edit.setText(str(suggestion))

    def _choose_workdir(self):  # pragma: no cover - GUI
        path = QtWidgets.QFileDialog.getExistingDirectory(self, "Workdir")
        if path:
            self.workdir_edit.setText(path)

    def _start_job(self):  # pragma: no cover - GUI
        job = PipelineJob()
        job.source = Path(self.source_edit.text()) if self.source_edit.text() else None
        job.workdir = Path(self.workdir_edit.text()) if self.workdir_edit.text() else None
        job.model_size = self.model_input.text() or "large-v3"
        job.beam_size = self.beam_slider.value()
        job.vad = self.vad_check.isChecked()
        job.mono = self.mono_check.isChecked()
        job.generate_romaji = self.romaji_check.isChecked()
        job.languages = [lang.strip() for lang in self.lang_edit.text().split(",") if lang.strip()]
        job.bilingual = self.bilingual_edit.text() or None
        job.fmt = self.fmt_combo.currentText()

        self.log_view.append("Iniciando...")
        worker = PipelineWorker(job)
        worker.signals.log.connect(self.log_view.append)
        worker.signals.failed.connect(lambda msg: self.log_view.append(f"Erro: {msg}"))
        worker.signals.results.connect(self._populate_results)
        if self.thread_pool:
            self.thread_pool.start(worker)

    def _populate_results(self, items: List[Path]):  # pragma: no cover - GUI
        self.results_list.clear()
        for item in items:
            self.results_list.addItem(str(item))


class FinalizeTab(BaseWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.thread_pool = QtCore.QThreadPool.globalInstance() if QtCore else None
        self._setup_ui()

    def _setup_ui(self):
        layout = QtWidgets.QVBoxLayout(self)
        self.video_edit = QtWidgets.QLineEdit()
        self.subs_edit = QtWidgets.QLineEdit()

        video_btn = QtWidgets.QPushButton("Escolher vídeo")
        video_btn.clicked.connect(self._choose_video)
        subs_btn = QtWidgets.QPushButton("Escolher legenda")
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
        form.addRow("Modo", self.mode_combo)
        form.addRow("Codec", self.codec_edit)
        form.addRow("CRF", self.crf_spin)

        self.run_btn = QtWidgets.QPushButton("Rodar")
        self.run_btn.clicked.connect(self._start_job)
        self.log_view = QtWidgets.QTextEdit()
        self.log_view.setReadOnly(True)

        layout.addLayout(video_row)
        layout.addLayout(subs_row)
        layout.addLayout(form)
        layout.addWidget(self.run_btn)
        layout.addWidget(self.log_view)

    def _choose_video(self):  # pragma: no cover - GUI
        path, _ = QtWidgets.QFileDialog.getOpenFileName(self, "Vídeo")
        if path:
            self.video_edit.setText(path)

    def _choose_subs(self):  # pragma: no cover - GUI
        path, _ = QtWidgets.QFileDialog.getOpenFileName(self, "Legenda")
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
        worker.signals.failed.connect(lambda msg: self.log_view.append(f"Erro: {msg}"))
        worker.signals.results.connect(lambda items: self.log_view.append(f"Saída: {items[0]}"))
        if self.thread_pool:
            self.thread_pool.start(worker)


class SettingsTab(BaseWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QtWidgets.QVBoxLayout(self)
        layout.addWidget(QtWidgets.QLabel("Configure caminhos e defaults no arquivo config.toml em %APPDATA%/jp2subs."))


class MainWindow(QtWidgets.QMainWindow if QtWidgets else object):  # type: ignore[misc]
    def __init__(self):
        if not QtWidgets:
            raise RuntimeError("PySide6 é necessário para a GUI")
        super().__init__()
        self.setWindowTitle("jp2subs")
        tabs = QtWidgets.QTabWidget()
        tabs.addTab(PipelineTab(), "Pipeline")
        tabs.addTab(FinalizeTab(), "Finalize")
        tabs.addTab(SettingsTab(), "Settings")
        self.setCentralWidget(tabs)

