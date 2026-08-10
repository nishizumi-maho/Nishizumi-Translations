"""Finalize page: attach, mux or burn an existing subtitle into a video."""
from __future__ import annotations

from pathlib import Path

from PySide6 import QtCore, QtGui, QtWidgets

from ...runtime.manager import manager
from .. import theme
from ..common import Banner, Card, Collapsible, IconButton, ScrollPage, hline, label, reveal
from ..state import FinalizeJob
from ..workers import FinalizeWorker

MODES = (
    (
        "sidecar",
        "Sidecar file",
        "Copies the subtitle next to the video with a matching name. Instant, nothing is re-encoded.",
    ),
    (
        "softcode",
        "Soft-mux into the video",
        "Embeds the subtitle as a selectable track. Fast, and the picture is untouched.",
    ),
    (
        "hardcode",
        "Burn into the picture",
        "Renders the subtitle permanently into the video. Slow, but plays anywhere.",
    ),
)


def ass_color(color: QtGui.QColor, alpha_percent: int = 100) -> str:
    """Convert a colour to the ``&HAABBGGRR`` string libass expects."""

    transparency = int(round(255 * (100 - max(0, min(100, alpha_percent))) / 100))
    return f"&H{transparency:02X}{color.blue():02X}{color.green():02X}{color.red():02X}"


def color_from_ass(value: str) -> QtGui.QColor:
    text = (value or "").strip().lstrip("&").lstrip("hH")
    if len(text) == 8:
        text = text[2:]
    if len(text) != 6:
        return QtGui.QColor("#ffffff")
    blue, green, red = text[0:2], text[2:4], text[4:6]
    return QtGui.QColor(int(red, 16), int(green, 16), int(blue, 16))


class ColorField(QtWidgets.QWidget):
    """Swatch button that stores an ASS colour string."""

    changed = QtCore.Signal(str)

    def __init__(self, initial: str = "&H00FFFFFF", parent: QtWidgets.QWidget | None = None):
        super().__init__(parent)
        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        self._color = color_from_ass(initial)
        self._alpha = 100

        self._button = QtWidgets.QPushButton("Choose colour")
        self._button.clicked.connect(self._pick)
        self._swatch = QtWidgets.QFrame()
        self._swatch.setFixedSize(28, 24)
        layout.addWidget(self._swatch, 0)
        layout.addWidget(self._button, 0)
        layout.addStretch(1)
        self._repaint()

    def _repaint(self) -> None:
        border = theme.active_palette().border_strong
        self._swatch.setStyleSheet(
            f"background-color: {self._color.name()}; border: 1px solid {border}; border-radius: 6px;"
        )

    def _pick(self) -> None:
        chosen = QtWidgets.QColorDialog.getColor(self._color, self, "Subtitle colour")
        if chosen.isValid():
            self._color = chosen
            self._repaint()
            self.changed.emit(self.value())

    def retheme(self) -> None:
        self._repaint()

    def set_alpha(self, percent: int) -> None:
        self._alpha = percent

    def value(self) -> str:
        return ass_color(self._color, self._alpha)


class FinalizePage(ScrollPage):
    """Turn a subtitle file plus a video into a deliverable."""

    navigate = QtCore.Signal(str)

    def __init__(self, parent: QtWidgets.QWidget | None = None):
        super().__init__(
            "Finalize",
            "Attach, embed or burn subtitles into a video with FFmpeg.",
            parent,
        )
        self._worker: FinalizeWorker | None = None
        self._result: Path | None = None

        self.readiness = Banner("", "warning", "Open Components")
        self.readiness.action_clicked.connect(lambda: self.navigate.emit("components"))
        self.content.addWidget(self.readiness)

        self._build_files_card()
        self._build_mode_card()
        self._build_style_card()
        self._build_run_row()
        self._build_status_card()
        self.content.addStretch(1)

        self._on_mode_changed(0)
        self.refresh_components()

    # -- construction -----------------------------------------------------

    def _picker_row(self, placeholder: str, title: str, filters: str) -> tuple[QtWidgets.QHBoxLayout, QtWidgets.QLineEdit]:
        row = QtWidgets.QHBoxLayout()
        row.setSpacing(8)
        edit = QtWidgets.QLineEdit()
        edit.setPlaceholderText(placeholder)
        button = QtWidgets.QPushButton("Browse")

        def choose() -> None:
            path, _ = QtWidgets.QFileDialog.getOpenFileName(self, title, "", filters)
            if path:
                edit.setText(path)

        button.clicked.connect(choose)
        row.addWidget(edit, 1)
        row.addWidget(button, 0)
        return row, edit

    def _build_files_card(self) -> None:
        card = Card("Input files", "", icon_name="film")
        form = QtWidgets.QFormLayout()
        form.setSpacing(11)
        form.setFieldGrowthPolicy(QtWidgets.QFormLayout.AllNonFixedFieldsGrow)

        video_row, self.video_edit = self._picker_row(
            "Path to the video file",
            "Choose a video",
            "Video files (*.mp4 *.mkv *.webm *.mov *.avi);;All files (*)",
        )
        form.addRow("Video", video_row)

        subs_row, self.subs_edit = self._picker_row(
            "Path to the subtitle file",
            "Choose a subtitle",
            "Subtitles (*.srt *.vtt *.ass);;All files (*)",
        )
        form.addRow("Subtitle", subs_row)

        out_row = QtWidgets.QHBoxLayout()
        out_row.setSpacing(8)
        self.out_dir_edit = QtWidgets.QLineEdit()
        self.out_dir_edit.setPlaceholderText("Same folder as the video")
        out_btn = QtWidgets.QPushButton("Browse")
        out_btn.clicked.connect(self._choose_out_dir)
        out_row.addWidget(self.out_dir_edit, 1)
        out_row.addWidget(out_btn, 0)
        form.addRow("Save to", out_row)

        card.body.addLayout(form)
        self.content.addWidget(card)

    def _build_mode_card(self) -> None:
        card = Card("What should happen?", "", icon_name="sliders")

        self.mode_combo = QtWidgets.QComboBox()
        for key, title, _description in MODES:
            self.mode_combo.addItem(title, key)
        self.mode_combo.currentIndexChanged.connect(self._on_mode_changed)
        card.body.addWidget(self.mode_combo)

        self.mode_hint = label("", "CardHint")
        card.body.addWidget(self.mode_hint)

        self.container_row = QtWidgets.QWidget()
        container_layout = QtWidgets.QHBoxLayout(self.container_row)
        container_layout.setContentsMargins(0, 0, 0, 0)
        container_layout.setSpacing(10)
        container_layout.addWidget(label("Container", "CardHint"), 0)
        self.container_combo = QtWidgets.QComboBox()
        self.container_combo.addItems(["mkv", "mp4"])
        self.container_combo.setToolTip("MKV accepts ASS and SRT. MP4 only accepts SRT or VTT.")
        container_layout.addWidget(self.container_combo, 0)
        container_layout.addStretch(1)
        card.body.addWidget(self.container_row)

        self.content.addWidget(card)

    def _build_style_card(self) -> None:
        self.style_card = Card(
            "Burn-in appearance",
            "Only applies when burning the subtitle into the picture.",
            icon_name="spark",
        )

        encode_form = QtWidgets.QFormLayout()
        encode_form.setSpacing(10)
        encode_form.setFieldGrowthPolicy(QtWidgets.QFormLayout.AllNonFixedFieldsGrow)

        self.codec_edit = QtWidgets.QLineEdit("libx264")
        encode_form.addRow("Video codec", self.codec_edit)

        self.crf_spin = QtWidgets.QSpinBox()
        self.crf_spin.setRange(10, 40)
        self.crf_spin.setValue(18)
        self.crf_spin.setToolTip("Lower is better quality and a bigger file. 18 is visually lossless.")
        encode_form.addRow("Quality (CRF)", self.crf_spin)

        self.preset_combo = QtWidgets.QComboBox()
        self.preset_combo.addItems(
            ["ultrafast", "superfast", "veryfast", "faster", "fast", "medium", "slow", "slower", "veryslow"]
        )
        self.preset_combo.setCurrentText("slow")
        encode_form.addRow("Encoder preset", self.preset_combo)

        self.style_card.body.addLayout(encode_form)
        self.style_card.body.addWidget(hline())

        style_section = Collapsible("Subtitle styling", expanded=False)
        style_form = QtWidgets.QFormLayout()
        style_form.setSpacing(10)
        style_form.setFieldGrowthPolicy(QtWidgets.QFormLayout.AllNonFixedFieldsGrow)

        self.font_edit = QtWidgets.QLineEdit()
        self.font_edit.setPlaceholderText("Leave blank to use the subtitle's own font")
        style_form.addRow("Font", self.font_edit)

        self.font_size_spin = QtWidgets.QSpinBox()
        self.font_size_spin.setRange(10, 96)
        self.font_size_spin.setValue(36)
        style_form.addRow("Font size", self.font_size_spin)

        weight_row = QtWidgets.QHBoxLayout()
        self.bold_check = QtWidgets.QCheckBox("Bold")
        self.italic_check = QtWidgets.QCheckBox("Italic")
        weight_row.addWidget(self.bold_check)
        weight_row.addWidget(self.italic_check)
        weight_row.addStretch(1)
        style_form.addRow("Style", weight_row)

        self.primary_color = ColorField("&H00FFFFFF")
        style_form.addRow("Text colour", self.primary_color)

        self.outline_spin = QtWidgets.QSpinBox()
        self.outline_spin.setRange(0, 10)
        self.outline_spin.setValue(2)
        style_form.addRow("Outline", self.outline_spin)

        self.shadow_spin = QtWidgets.QSpinBox()
        self.shadow_spin.setRange(0, 10)
        self.shadow_spin.setValue(1)
        style_form.addRow("Shadow", self.shadow_spin)

        self.background_check = QtWidgets.QCheckBox("Draw a box behind the text")
        style_form.addRow("Background", self.background_check)

        self.background_color = ColorField("&H80000000")
        style_form.addRow("Box colour", self.background_color)

        self.background_opacity = QtWidgets.QSpinBox()
        self.background_opacity.setRange(0, 100)
        self.background_opacity.setValue(50)
        self.background_opacity.setSuffix(" %")
        style_form.addRow("Box opacity", self.background_opacity)

        self.alignment_combo = QtWidgets.QComboBox()
        for text, value in (
            ("Bottom centre", 2),
            ("Bottom left", 1),
            ("Bottom right", 3),
            ("Middle centre", 5),
            ("Middle left", 4),
            ("Middle right", 6),
            ("Top centre", 8),
            ("Top left", 7),
            ("Top right", 9),
        ):
            self.alignment_combo.addItem(text, value)
        style_form.addRow("Position", self.alignment_combo)

        self.margin_spin = QtWidgets.QSpinBox()
        self.margin_spin.setRange(0, 200)
        self.margin_spin.setValue(20)
        style_form.addRow("Edge margin", self.margin_spin)

        style_section.body.addLayout(style_form)
        self.style_card.body.addWidget(style_section)
        self.content.addWidget(self.style_card)

    def _build_run_row(self) -> None:
        row = QtWidgets.QHBoxLayout()
        row.setSpacing(10)
        self.run_btn = IconButton("Run", "play", primary=True)
        self.run_btn.setMinimumHeight(38)
        self.run_btn.clicked.connect(self._start)

        self.cancel_btn = QtWidgets.QPushButton("Cancel")
        self.cancel_btn.setMinimumHeight(38)
        self.cancel_btn.setEnabled(False)
        self.cancel_btn.clicked.connect(self._cancel)

        row.addWidget(self.run_btn, 0)
        row.addWidget(self.cancel_btn, 0)
        row.addStretch(1)

        holder = QtWidgets.QWidget()
        holder.setLayout(row)
        self.content.addWidget(holder)

    def _build_status_card(self) -> None:
        self.status_card = Card("Status", "", icon_name="waveform")

        self.progress_bar = QtWidgets.QProgressBar()
        self.progress_bar.setRange(0, 0)
        self.progress_bar.setTextVisible(False)
        self.status_card.body.addWidget(self.progress_bar)

        self.status_label = label("", "CardHint")
        self.status_card.body.addWidget(self.status_label)

        self.open_btn = IconButton("Open output folder", "folder")
        self.open_btn.clicked.connect(lambda: reveal(self._result) if self._result else None)
        self.open_btn.setVisible(False)
        row = QtWidgets.QHBoxLayout()
        row.addWidget(self.open_btn, 0)
        row.addStretch(1)
        self.status_card.body.addLayout(row)

        self.status_card.setVisible(False)
        self.content.addWidget(self.status_card)

    # -- behaviour --------------------------------------------------------

    def refresh_components(self) -> None:
        ready = bool(manager.ffmpeg_binary()) or _ffmpeg_on_path()
        self.readiness.setVisible(not ready)
        if not ready:
            self.readiness.set_message(
                "FFmpeg is required to mux or burn subtitles. Install it from the Components page.",
                "warning",
                "Open Components",
            )
        self.run_btn.setEnabled(ready and self._worker is None)

    def _on_mode_changed(self, index: int) -> None:
        key = self.mode_combo.itemData(index) or "sidecar"
        self.mode_hint.setText(next(text for mode, _title, text in MODES if mode == key))
        self.container_row.setVisible(key == "softcode")
        self.style_card.setVisible(key == "hardcode")

    def _choose_out_dir(self) -> None:
        path = QtWidgets.QFileDialog.getExistingDirectory(self, "Choose an output folder")
        if path:
            self.out_dir_edit.setText(path)

    def set_subtitle(self, path: str) -> None:
        """Pre-fill the subtitle field, used when arriving from the Transcribe page."""

        self.subs_edit.setText(str(path))

    def _build_job(self) -> FinalizeJob | None:
        job = FinalizeJob()
        video_text = self.video_edit.text().strip()
        subtitle_text = self.subs_edit.text().strip()
        job.video = Path(video_text) if video_text else None
        job.subtitle = Path(subtitle_text) if subtitle_text else None

        if not job.video or not job.video.exists():
            QtWidgets.QMessageBox.warning(self, "Video missing", "Choose a video file that exists.")
            return None
        if not job.subtitle or not job.subtitle.exists():
            QtWidgets.QMessageBox.warning(self, "Subtitle missing", "Choose a subtitle file that exists.")
            return None

        out_dir_text = self.out_dir_edit.text().strip()
        job.out_dir = Path(out_dir_text) if out_dir_text else None
        job.mode = self.mode_combo.currentData() or "sidecar"
        job.container = self.container_combo.currentText()
        job.codec = self.codec_edit.text().strip() or "libx264"
        job.crf = self.crf_spin.value()
        job.preset = self.preset_combo.currentText()
        job.font = self.font_edit.text().strip() or None
        job.font_size = self.font_size_spin.value()
        job.bold = self.bold_check.isChecked()
        job.italic = self.italic_check.isChecked()
        job.outline = self.outline_spin.value()
        job.shadow = self.shadow_spin.value()
        job.margin_v = self.margin_spin.value()
        job.alignment = int(self.alignment_combo.currentData())
        job.primary_color = self.primary_color.value()
        job.background_enabled = self.background_check.isChecked()
        self.background_color.set_alpha(self.background_opacity.value())
        job.background_color = self.background_color.value()
        return job

    def _start(self) -> None:
        job = self._build_job()
        if not job:
            return

        self._result = None
        self.status_card.setVisible(True)
        self.progress_bar.setRange(0, 0)
        self.progress_bar.setVisible(True)
        self.open_btn.setVisible(False)
        self.status_label.setText("Working... FFmpeg is running.")
        self.run_btn.setEnabled(False)
        self.cancel_btn.setEnabled(True)

        worker = FinalizeWorker(job)
        self._worker = worker
        worker.signals.stage.connect(self.status_label.setText)
        worker.signals.failed.connect(self._on_failed)
        worker.signals.cancelled.connect(self._on_cancelled)
        worker.signals.results.connect(self._on_results)
        worker.signals.finished.connect(self._on_finished)
        QtCore.QThreadPool.globalInstance().start(worker)

    def _cancel(self) -> None:
        if self._worker:
            self._worker.cancel()
            self.status_label.setText("Cancelling...")

    @QtCore.Slot(list)
    def _on_results(self, items: list) -> None:
        if items:
            self._result = Path(items[0])

    def _on_finished(self) -> None:
        self._worker = None
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(100)
        self.status_label.setText(f"Done: {self._result}" if self._result else "Done.")
        self.open_btn.setVisible(bool(self._result))
        self._reset_controls()

    def _on_failed(self, message: str) -> None:
        self._worker = None
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.status_label.setText(f"Failed: {message}")
        self._reset_controls()
        QtWidgets.QMessageBox.critical(self, "Finalize failed", message)

    def _on_cancelled(self) -> None:
        self._worker = None
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.status_label.setText("Cancelled.")
        self._reset_controls()

    def _reset_controls(self) -> None:
        self.cancel_btn.setEnabled(False)
        self.refresh_components()


def _ffmpeg_on_path() -> bool:
    import shutil

    return shutil.which("ffmpeg") is not None
