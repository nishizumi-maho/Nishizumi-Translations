"""Background jobs for the GUI.

Everything here runs on the shared :class:`QThreadPool` and talks back to the
UI through signals, so no worker ever touches a widget directly.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

from .. import video
from ..pipeline import PipelineCallbacks, PipelineRunner
from ..runtime.download import DownloadCancelled, Progress
from ..runtime.manager import manager
from ..runtime.updater import ReleaseInfo, check_for_updates, download_update
from .state import FinalizeJob, PipelineJob

try:  # pragma: no cover - optional dependency
    from PySide6 import QtCore
except Exception:  # pragma: no cover - allow import without Qt
    QtCore = None  # type: ignore


class WorkerSignals(QtCore.QObject if QtCore else object):  # type: ignore[misc]
    if QtCore:  # pragma: no cover - type guarded
        finished = QtCore.Signal()
        failed = QtCore.Signal(str)
        cancelled = QtCore.Signal()
        progress = QtCore.Signal(int)
        stage = QtCore.Signal(str)
        detail = QtCore.Signal(str)
        results = QtCore.Signal(list)
        log = QtCore.Signal(str)
        stage_started = QtCore.Signal(str)
        stage_done = QtCore.Signal(str)
        item_started = QtCore.Signal(str)
        item_done = QtCore.Signal(str, list)


class PipelineWorker(QtCore.QRunnable if QtCore else object):  # type: ignore[misc]
    def __init__(self, job: PipelineJob):
        super().__init__()
        self.job = job
        self.signals = WorkerSignals()
        self._cancelled = False
        self._processes: list[subprocess.Popen] = []
        self._runner: PipelineRunner | None = None

    def run(self):  # pragma: no cover - GUI thread
        try:
            self._execute()
            if not self._cancelled:
                self.signals.finished.emit()
        except Exception as exc:  # noqa: BLE001
            if self._cancelled:
                self.signals.cancelled.emit()
            else:
                self.signals.failed.emit(str(exc))
        finally:
            self._runner = None
            self._processes.clear()

    def cancel(self):  # pragma: no cover - GUI thread
        self._cancelled = True
        if self._runner:
            self._runner.cancel()
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
            on_subprocess=self._register_process,
        )
        self._runner = PipelineRunner(callbacks)
        outputs = self._runner.run(self.job)
        self.signals.results.emit(list(outputs))

    def _emit_progress(self, event):  # pragma: no cover - GUI thread
        self.signals.progress.emit(event.percent)
        self.signals.stage.emit(event.message)
        self.signals.detail.emit(event.detail or "")

    def _register_process(self, proc: subprocess.Popen) -> None:  # pragma: no cover - GUI thread
        self._processes.append(proc)


class FinalizeWorker(QtCore.QRunnable if QtCore else object):  # type: ignore[misc]
    def __init__(self, job: FinalizeJob):
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
            if self._cancelled:
                self.signals.cancelled.emit()
            else:
                self.signals.failed.emit(str(exc))
        finally:
            self._processes.clear()

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
        if not self.job.video or not self.job.subtitle:
            raise RuntimeError("Video or subtitle missing")
        out_dir = self.job.out_dir or self.job.video.parent
        self.signals.stage.emit(f"Running {self.job.mode}...")

        if self.job.mode == "sidecar":
            out = video.build_out_path(self.job.video, self.job.subtitle, out_dir, True, None, None, mode="sidecar")
            result = video.copy_sidecar(self.job.video, self.job.subtitle, out)
        elif self.job.mode == "softcode":
            container = self.job.container or "mkv"
            out = video.build_out_path(
                self.job.video, self.job.subtitle, out_dir, True, None, container, mode="softcode"
            )
            result = video.run_ffmpeg_mux_soft(
                self.job.video,
                self.job.subtitle,
                out,
                container=container,
                lang="ja",
                register_subprocess=self._register_process,
            )
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
                register_subprocess=self._register_process,
            )
        self.signals.results.emit([Path(result)])

    def _register_process(self, proc: subprocess.Popen) -> None:  # pragma: no cover - GUI thread
        self._processes.append(proc)


class DownloadSignals(QtCore.QObject if QtCore else object):  # type: ignore[misc]
    if QtCore:  # pragma: no cover - type guarded
        #: component key, 0-100 (or -1 for indeterminate)
        progress = QtCore.Signal(str, int)
        #: component key, human readable detail line
        detail = QtCore.Signal(str, str)
        #: component key
        finished = QtCore.Signal(str)
        cancelled = QtCore.Signal(str)
        #: component key, error message
        failed = QtCore.Signal(str, str)


class ComponentInstallWorker(QtCore.QRunnable if QtCore else object):  # type: ignore[misc]
    """Downloads and installs one catalog component."""

    def __init__(self, key: str):
        super().__init__()
        self.key = key
        self.signals = DownloadSignals()
        self._cancelled = False

    def cancel(self) -> None:
        self._cancelled = True

    def run(self):  # pragma: no cover - GUI thread
        try:
            manager.install(self.key, on_progress=self._on_progress, is_cancelled=lambda: self._cancelled)
        except DownloadCancelled:
            self.signals.cancelled.emit(self.key)
        except Exception as exc:  # noqa: BLE001
            self.signals.failed.emit(self.key, str(exc))
        else:
            self.signals.finished.emit(self.key)

    def _on_progress(self, progress: Progress) -> None:  # pragma: no cover - GUI thread
        self.signals.progress.emit(self.key, progress.percent)
        self.signals.detail.emit(self.key, _format_progress(progress))


class UpdateSignals(QtCore.QObject if QtCore else object):  # type: ignore[misc]
    if QtCore:  # pragma: no cover - type guarded
        #: emits the release when one is newer, or None
        checked = QtCore.Signal(object)
        failed = QtCore.Signal(str)
        progress = QtCore.Signal(int)
        detail = QtCore.Signal(str)
        downloaded = QtCore.Signal(str)


class UpdateCheckWorker(QtCore.QRunnable if QtCore else object):  # type: ignore[misc]
    def __init__(self, include_prerelease: bool = False):
        super().__init__()
        self.include_prerelease = include_prerelease
        self.signals = UpdateSignals()

    def run(self):  # pragma: no cover - GUI thread
        try:
            release = check_for_updates(include_prerelease=self.include_prerelease)
        except Exception as exc:  # noqa: BLE001
            self.signals.failed.emit(str(exc))
            return
        self.signals.checked.emit(release)


class UpdateDownloadWorker(QtCore.QRunnable if QtCore else object):  # type: ignore[misc]
    def __init__(self, release: ReleaseInfo):
        super().__init__()
        self.release = release
        self.signals = UpdateSignals()
        self._cancelled = False

    def cancel(self) -> None:
        self._cancelled = True

    def run(self):  # pragma: no cover - GUI thread
        try:
            path = download_update(
                self.release,
                on_progress=self._on_progress,
                is_cancelled=lambda: self._cancelled,
            )
        except DownloadCancelled:
            return
        except Exception as exc:  # noqa: BLE001
            self.signals.failed.emit(str(exc))
            return
        self.signals.downloaded.emit(str(path))

    def _on_progress(self, progress: Progress) -> None:  # pragma: no cover - GUI thread
        self.signals.progress.emit(progress.percent)
        self.signals.detail.emit(_format_progress(progress))


def _format_progress(progress: Progress) -> str:
    """Turn a raw progress tick into the one-line status a user reads."""

    from ..runtime.store import human_size

    if progress.total and progress.downloaded:
        parts = [f"{human_size(progress.downloaded)} of {human_size(progress.total)}"]
        if progress.speed_bps:
            parts.append(f"{human_size(progress.speed_bps)}/s")
        if progress.eta_seconds and progress.eta_seconds > 1:
            parts.append(f"{_format_eta(progress.eta_seconds)} left")
        return " · ".join(parts)
    return progress.detail or progress.label


def _format_eta(seconds: float) -> str:
    seconds = int(seconds)
    if seconds < 60:
        return f"{seconds}s"
    minutes, secs = divmod(seconds, 60)
    if minutes < 60:
        return f"{minutes}m {secs:02d}s"
    hours, minutes = divmod(minutes, 60)
    return f"{hours}h {minutes:02d}m"
