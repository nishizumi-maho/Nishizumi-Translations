"""Background workers for GUI tasks."""
from __future__ import annotations

import subprocess
from pathlib import Path
from typing import List

from .. import video
from ..pipeline import PipelineCallbacks, PipelineRunner
from .state import FinalizeJob, PipelineJob

try:  # pragma: no cover - optional dependency
    from PySide6 import QtCore
except Exception:  # pragma: no cover - allow import without Qt
    QtCore = None  # type: ignore


class PipelineWorker(QtCore.QRunnable if QtCore else object):  # type: ignore[misc]
    def __init__(self, job: PipelineJob):
        super().__init__()
        self.job = job
        self.signals = WorkerSignals()
        self._cancelled = False
        self._processes: list[subprocess.Popen] = []

    def run(self):  # pragma: no cover - GUI thread
        try:
            self._execute()
            if not self._cancelled:
                self.signals.finished.emit()
        except Exception as exc:  # noqa: BLE001
            self.signals.failed.emit(str(exc))

    def cancel(self):  # pragma: no cover - GUI thread
        self._cancelled = True
        for proc in self._processes:
            if proc.poll() is None:
                proc.terminate()
                try:
                    proc.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    proc.kill()

    def _execute(self):  # pragma: no cover - GUI thread
        callbacks = PipelineCallbacks(
            on_stage_start=lambda name: self.signals.stage_started.emit(name),
            on_stage_done=lambda name: self.signals.stage_done.emit(name),
            on_stage_progress=self._emit_progress,
            on_log=self.signals.log.emit,
            on_item_start=lambda path: self.signals.item_started.emit(str(path)),
            on_item_done=lambda path, outputs: self.signals.item_done.emit(str(path), outputs),
        )
        runner = PipelineRunner(callbacks)
        runner.run(self.job)

    def _emit_progress(self, event):  # pragma: no cover - GUI thread
        self.signals.progress.emit(event.percent)
        self.signals.stage.emit(event.message)
        self.signals.detail.emit(event.detail or "")


class FinalizeWorker(QtCore.QRunnable if QtCore else object):  # type: ignore[misc]
    def __init__(self, job: FinalizeJob):
        super().__init__()
        self.job = job
        self.signals = WorkerSignals()
        self._cancelled = False

    def run(self):  # pragma: no cover - GUI thread
        try:
            self._execute()
            if not self._cancelled:
                self.signals.finished.emit()
        except Exception as exc:  # noqa: BLE001
            self.signals.failed.emit(str(exc))

    def cancel(self):  # pragma: no cover - GUI thread
        self._cancelled = True

    def _execute(self):  # pragma: no cover - GUI thread
        if not self.job.video or not self.job.subtitle:
            raise RuntimeError("Video or subtitle missing")
        out_dir = self.job.out_dir or self.job.video.parent
        if self.job.mode == "sidecar":
            out = video.build_out_path(self.job.video, self.job.subtitle, out_dir, True, None, None, mode="sidecar")
            result = video.copy_sidecar(self.job.video, self.job.subtitle, out)
        elif self.job.mode == "softcode":
            out = video.build_out_path(self.job.video, self.job.subtitle, out_dir, True, None, "mkv", mode="softcode")
            result = video.run_ffmpeg_mux_soft(self.job.video, self.job.subtitle, out, container="mkv")
        else:
            out = video.build_out_path(self.job.video, self.job.subtitle, out_dir, True, None, "mp4", mode="hardcode")
            styles = {
                "Fontsize": str(self.job.font_size),
                "Bold": "1" if self.job.bold else "0",
                "Italic": "1" if self.job.italic else "0",
                "Outline": str(self.job.outline),
                "Shadow": str(self.job.shadow),
                "MarginV": str(self.job.margin_v),
                "Alignment": str(self.job.alignment),
                "PrimaryColour": self.job.primary_color,
                "BorderStyle": "3" if self.job.background_enabled else "1",
            }
            if self.job.background_enabled:
                styles["BackColour"] = self.job.background_color
            result = video.run_ffmpeg_burn(
                self.job.video,
                self.job.subtitle,
                out,
                codec=self.job.codec,
                crf=self.job.crf,
                preset=self.job.preset,
                font=self.job.font,
                styles=styles,
            )
        self.signals.results.emit([Path(result)])


class WorkerSignals(QtCore.QObject if QtCore else object):  # type: ignore[misc]
    if QtCore:  # pragma: no cover - type guarded
        finished = QtCore.Signal()
        failed = QtCore.Signal(str)
        progress = QtCore.Signal(int)
        stage = QtCore.Signal(str)
        detail = QtCore.Signal(str)
        results = QtCore.Signal(list)
        log = QtCore.Signal(str)
        stage_started = QtCore.Signal(str)
        stage_done = QtCore.Signal(str)
        item_started = QtCore.Signal(str)
        item_done = QtCore.Signal(str, list)
    else:  # pragma: no cover - no Qt
        pass
