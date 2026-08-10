"""Settings page: preferences, tool paths and pipeline defaults."""
from __future__ import annotations

from PySide6 import QtCore, QtWidgets

from ...config import AppConfig, detect_ffmpeg
from ...runtime import store
from ...runtime.manager import manager
from ..common import Card, Collapsible, IconButton, ScrollPage, label, reveal
from ..state import load_app_state, persist_app_state
from .transcribe import parse_extra_args


class SettingsPage(ScrollPage):
    """Everything persisted to ``config.toml``, grouped by what it affects."""

    theme_changed = QtCore.Signal(str)
    navigate = QtCore.Signal(str)
    settings_saved = QtCore.Signal()

    def __init__(self, parent: QtWidgets.QWidget | None = None):
        super().__init__("Settings", "Preferences are saved to your user profile.", parent)
        self.cfg = load_app_state()

        self._build_appearance_card()
        self._build_updates_card()
        self._build_tools_card()
        self._build_defaults_card()
        self._build_buttons()
        self.content.addStretch(1)

        self._sync_from_cfg()

    # -- construction -----------------------------------------------------

    def _build_appearance_card(self) -> None:
        card = Card("Appearance", "", icon_name="spark")
        form = QtWidgets.QFormLayout()
        form.setSpacing(11)
        form.setFieldGrowthPolicy(QtWidgets.QFormLayout.AllNonFixedFieldsGrow)

        self.theme_combo = QtWidgets.QComboBox()
        self.theme_combo.addItem("Dark", "dark")
        self.theme_combo.addItem("Light", "light")
        self.theme_combo.currentIndexChanged.connect(self._on_theme_changed)
        form.addRow("Theme", self.theme_combo)

        self.open_output_check = QtWidgets.QCheckBox("Open the output folder when a run finishes")
        form.addRow("After a run", self.open_output_check)

        card.body.addLayout(form)
        self.content.addWidget(card)

    def _build_updates_card(self) -> None:
        card = Card("Updates", "", icon_name="download")
        form = QtWidgets.QFormLayout()
        form.setSpacing(11)
        form.setFieldGrowthPolicy(QtWidgets.QFormLayout.AllNonFixedFieldsGrow)

        self.check_updates_check = QtWidgets.QCheckBox("Check for a new version when the app starts")
        form.addRow("On startup", self.check_updates_check)

        self.prerelease_check = QtWidgets.QCheckBox("Include pre-releases")
        form.addRow("Channel", self.prerelease_check)

        card.body.addLayout(form)

        row = QtWidgets.QHBoxLayout()
        check_now = IconButton("Check for updates now", "refresh")
        check_now.clicked.connect(lambda: self.navigate.emit("about"))
        row.addWidget(check_now, 0)
        row.addStretch(1)
        card.body.addLayout(row)

        self.content.addWidget(card)

    def _build_tools_card(self) -> None:
        card = Card(
            "Tools and storage",
            "Leave the FFmpeg path empty to use the copy the app installed.",
            icon_name="cpu",
        )
        form = QtWidgets.QFormLayout()
        form.setSpacing(11)
        form.setFieldGrowthPolicy(QtWidgets.QFormLayout.AllNonFixedFieldsGrow)

        ffmpeg_row = QtWidgets.QHBoxLayout()
        ffmpeg_row.setSpacing(8)
        self.ffmpeg_edit = QtWidgets.QLineEdit()
        self.ffmpeg_edit.setPlaceholderText("Managed automatically")
        browse_btn = QtWidgets.QPushButton("Browse")
        browse_btn.clicked.connect(self._choose_ffmpeg)
        detect_btn = QtWidgets.QPushButton("Detect")
        detect_btn.clicked.connect(self._detect_ffmpeg)
        ffmpeg_row.addWidget(self.ffmpeg_edit, 1)
        ffmpeg_row.addWidget(browse_btn, 0)
        ffmpeg_row.addWidget(detect_btn, 0)
        form.addRow("FFmpeg path", ffmpeg_row)

        self.ffmpeg_status = label("", "Faint")
        form.addRow("", self.ffmpeg_status)

        card.body.addLayout(form)

        row = QtWidgets.QHBoxLayout()
        self.storage_label = label("", "CardHint")
        row.addWidget(self.storage_label, 1)
        open_data = IconButton("Open data folder", "folder")
        open_data.clicked.connect(lambda: reveal(store.data_dir()))
        row.addWidget(open_data, 0)
        manage = IconButton("Manage components", "download")
        manage.clicked.connect(lambda: self.navigate.emit("components"))
        row.addWidget(manage, 0)
        card.body.addLayout(row)

        self.content.addWidget(card)

    def _build_defaults_card(self) -> None:
        card = Card("Transcription defaults", "Used for every new run.", icon_name="sliders")

        form = QtWidgets.QFormLayout()
        form.setSpacing(11)
        form.setFieldGrowthPolicy(QtWidgets.QFormLayout.AllNonFixedFieldsGrow)

        self.beam_spin = QtWidgets.QSpinBox()
        self.beam_spin.setRange(1, 20)
        form.addRow("Beam size", self.beam_spin)

        self.vad_check = QtWidgets.QCheckBox("Skip silence before transcribing")
        form.addRow("Voice detection", self.vad_check)

        self.mono_check = QtWidgets.QCheckBox("Downmix to mono during ingest")
        form.addRow("Audio", self.mono_check)

        self.format_combo = QtWidgets.QComboBox()
        self.format_combo.addItems(["srt", "vtt", "ass"])
        form.addRow("Subtitle format", self.format_combo)

        self.prefer_gpu_check = QtWidgets.QCheckBox("Use the GPU when one is available")
        form.addRow("Device", self.prefer_gpu_check)

        card.body.addLayout(form)

        advanced = Collapsible("Advanced ASR defaults")
        adv_form = QtWidgets.QFormLayout()
        adv_form.setSpacing(10)
        adv_form.setFieldGrowthPolicy(QtWidgets.QFormLayout.AllNonFixedFieldsGrow)

        self.best_of_spin = QtWidgets.QSpinBox()
        self.best_of_spin.setRange(0, 10)
        self.best_of_spin.setSpecialValueText("Automatic")
        adv_form.addRow("Best of", self.best_of_spin)

        self.patience_spin = QtWidgets.QDoubleSpinBox()
        self.patience_spin.setRange(0.0, 10.0)
        self.patience_spin.setDecimals(2)
        adv_form.addRow("Patience", self.patience_spin)

        self.length_penalty_spin = QtWidgets.QDoubleSpinBox()
        self.length_penalty_spin.setRange(-5.0, 5.0)
        self.length_penalty_spin.setDecimals(2)
        adv_form.addRow("Length penalty", self.length_penalty_spin)

        self.word_ts_check = QtWidgets.QCheckBox("Collect word-level timestamps")
        adv_form.addRow("Timing", self.word_ts_check)

        self.threads_spin = QtWidgets.QSpinBox()
        self.threads_spin.setRange(0, 64)
        self.threads_spin.setSpecialValueText("Automatic")
        adv_form.addRow("CPU threads", self.threads_spin)

        self.compute_combo = QtWidgets.QComboBox()
        self.compute_combo.addItems(["default", "float16", "int8", "int8_float16"])
        adv_form.addRow("Compute type", self.compute_combo)

        self.suppress_blank_check = QtWidgets.QCheckBox("Suppress blank output")
        adv_form.addRow("Suppression", self.suppress_blank_check)

        self.suppress_tokens_spin = QtWidgets.QSpinBox()
        self.suppress_tokens_spin.setRange(-1, 100000)
        adv_form.addRow("Suppress token (-1 = default)", self.suppress_tokens_spin)

        self.extra_args_edit = QtWidgets.QPlainTextEdit()
        self.extra_args_edit.setPlaceholderText("key=value pairs, one per line")
        self.extra_args_edit.setMaximumHeight(80)
        adv_form.addRow("Extra ASR args", self.extra_args_edit)

        advanced.body.addLayout(adv_form)
        card.body.addWidget(advanced)

        self.content.addWidget(card)

    def _build_buttons(self) -> None:
        row = QtWidgets.QHBoxLayout()
        row.setSpacing(10)

        save_btn = IconButton("Save settings", "check", primary=True)
        save_btn.setMinimumHeight(36)
        save_btn.clicked.connect(self.save)

        reload_btn = QtWidgets.QPushButton("Reload")
        reload_btn.setMinimumHeight(36)
        reload_btn.clicked.connect(self.reload)

        reset_btn = QtWidgets.QPushButton("Reset to defaults")
        reset_btn.setObjectName("Danger")
        reset_btn.setMinimumHeight(36)
        reset_btn.clicked.connect(self.reset)

        row.addWidget(save_btn, 0)
        row.addWidget(reload_btn, 0)
        row.addWidget(reset_btn, 0)
        row.addStretch(1)

        self.saved_label = label("", "Faint")
        row.addWidget(self.saved_label, 0)

        holder = QtWidgets.QWidget()
        holder.setLayout(row)
        self.content.addWidget(holder)

    # -- behaviour --------------------------------------------------------

    def _on_theme_changed(self) -> None:
        self.theme_changed.emit(self.theme_combo.currentData())

    def _choose_ffmpeg(self) -> None:
        pattern = "ffmpeg (ffmpeg.exe ffmpeg);;All files (*)"
        path, _ = QtWidgets.QFileDialog.getOpenFileName(self, "Select the ffmpeg binary", "", pattern)
        if path:
            self.ffmpeg_edit.setText(path)
            self._refresh_ffmpeg_status()

    def _detect_ffmpeg(self) -> None:
        detected = detect_ffmpeg(self.ffmpeg_edit.text().strip() or None)
        if detected:
            self.ffmpeg_edit.setText(detected)
        else:
            QtWidgets.QMessageBox.information(
                self,
                "FFmpeg not found",
                "No ffmpeg was found on PATH. Install it from the Components page and the app will use its own copy.",
            )
        self._refresh_ffmpeg_status()

    def _refresh_ffmpeg_status(self) -> None:
        managed = manager.ffmpeg_binary()
        configured = self.ffmpeg_edit.text().strip()
        if configured:
            self.ffmpeg_status.setText("Using the path above.")
        elif managed:
            self.ffmpeg_status.setText(f"Using the managed copy: {managed}")
        else:
            resolved = detect_ffmpeg(None)
            self.ffmpeg_status.setText(
                f"Using ffmpeg from PATH: {resolved}" if resolved else "No ffmpeg available yet."
            )
        total = manager.total_size()
        self.storage_label.setText(
            f"{store.human_size(total)} of components in {store.data_dir()}"
            if total
            else f"Nothing downloaded yet. Components will go to {store.data_dir()}"
        )

    def refresh_components(self) -> None:
        manager.refresh()
        self._refresh_ffmpeg_status()

    def _sync_from_cfg(self) -> None:
        cfg = self.cfg
        defaults = cfg.defaults

        theme_index = self.theme_combo.findData(cfg.app.theme)
        self.theme_combo.blockSignals(True)
        self.theme_combo.setCurrentIndex(max(theme_index, 0))
        self.theme_combo.blockSignals(False)

        self.open_output_check.setChecked(cfg.app.open_output_when_done)
        self.check_updates_check.setChecked(cfg.app.check_updates_on_start)
        self.prerelease_check.setChecked(cfg.app.include_prereleases)
        self.prefer_gpu_check.setChecked(cfg.app.prefer_gpu)

        self.ffmpeg_edit.setText(cfg.ffmpeg_path or "")
        self.beam_spin.setValue(defaults.beam_size)
        self.vad_check.setChecked(defaults.vad)
        self.mono_check.setChecked(defaults.mono)

        format_index = self.format_combo.findText(defaults.subtitle_format)
        if format_index >= 0:
            self.format_combo.setCurrentIndex(format_index)

        self.best_of_spin.setValue(defaults.best_of or 0)
        self.patience_spin.setValue(defaults.patience or 0.0)
        self.length_penalty_spin.setValue(defaults.length_penalty or 0.0)
        self.word_ts_check.setChecked(defaults.word_timestamps)
        self.threads_spin.setValue(defaults.threads or 0)

        compute_index = self.compute_combo.findText(defaults.compute_type or "default")
        if compute_index >= 0:
            self.compute_combo.setCurrentIndex(compute_index)

        self.suppress_blank_check.setChecked(defaults.suppress_blank)
        self.suppress_tokens_spin.setValue(defaults.suppress_tokens)
        self.extra_args_edit.setPlainText(
            "\n".join(f"{key}={value}" for key, value in (defaults.extra_asr_args or {}).items())
        )
        self._refresh_ffmpeg_status()

    def save(self) -> None:
        cfg = self.cfg
        cfg.app.theme = self.theme_combo.currentData()
        cfg.app.open_output_when_done = self.open_output_check.isChecked()
        cfg.app.check_updates_on_start = self.check_updates_check.isChecked()
        cfg.app.include_prereleases = self.prerelease_check.isChecked()
        cfg.app.prefer_gpu = self.prefer_gpu_check.isChecked()

        cfg.ffmpeg_path = self.ffmpeg_edit.text().strip() or None
        cfg.defaults.beam_size = self.beam_spin.value()
        cfg.defaults.vad = self.vad_check.isChecked()
        cfg.defaults.mono = self.mono_check.isChecked()
        cfg.defaults.subtitle_format = self.format_combo.currentText()
        cfg.defaults.best_of = self.best_of_spin.value() or None
        cfg.defaults.patience = self.patience_spin.value() or None
        cfg.defaults.length_penalty = self.length_penalty_spin.value() or None
        cfg.defaults.word_timestamps = self.word_ts_check.isChecked()
        cfg.defaults.threads = self.threads_spin.value() or None

        compute_type = self.compute_combo.currentText()
        cfg.defaults.compute_type = None if compute_type == "default" else compute_type
        cfg.defaults.suppress_blank = self.suppress_blank_check.isChecked()
        cfg.defaults.suppress_tokens = self.suppress_tokens_spin.value()
        cfg.defaults.extra_asr_args = parse_extra_args(self.extra_args_edit.toPlainText())

        persist_app_state(cfg)
        self.saved_label.setText("Saved")
        QtCore.QTimer.singleShot(2500, lambda: self.saved_label.setText(""))
        self.settings_saved.emit()

    def reload(self) -> None:
        self.cfg = load_app_state()
        self._sync_from_cfg()
        self.theme_changed.emit(self.cfg.app.theme)

    def reset(self) -> None:
        answer = QtWidgets.QMessageBox.question(
            self,
            "Reset settings?",
            "Every preference goes back to its default. Downloaded models and tools are kept.",
            QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No,
            QtWidgets.QMessageBox.No,
        )
        if answer != QtWidgets.QMessageBox.Yes:
            return
        self.cfg = AppConfig()
        self._sync_from_cfg()
        self.save()
        self.theme_changed.emit(self.cfg.app.theme)
