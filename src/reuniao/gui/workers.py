"""Background work, so the window never freezes on a long recording.

The download and relocation workers are deliberately this app's own rather
than the subtitle app's: importing that module would drag in its whole
pipeline — romanization, translation, video — none of which this app has any
use for, in the bundle or at startup.
"""
from __future__ import annotations

from pathlib import Path

from jp2subs.runtime import store
from jp2subs.runtime.download import DownloadCancelled, Progress
from jp2subs.runtime.manager import manager
from PySide6 import QtCore

from ..components import human_size
from ..pipeline import Cancelled, Job, Result, Runner, TrackJob
from ..progress import ProgressEvent


class TranscriptionSignals(QtCore.QObject):
    #: A ProgressEvent from the pipeline.
    progress = QtCore.Signal(object)
    #: One line for the run log.
    log = QtCore.Signal(str)
    #: The finished Result.
    finished = QtCore.Signal(object)
    cancelled = QtCore.Signal()
    #: Human-readable failure message.
    failed = QtCore.Signal(str)


class TranscriptionWorker(QtCore.QRunnable):
    """Runs one recording through the pipeline off the UI thread."""

    def __init__(self, job: Job | TrackJob):
        super().__init__()
        self.job = job
        self.signals = TranscriptionSignals()
        self._runner = Runner(
            on_progress=self._on_progress,
            on_log=self.signals.log.emit,
        )

    def cancel(self) -> None:
        self._runner.cancel()

    def run(self) -> None:  # pragma: no cover - runs on a worker thread
        try:
            if isinstance(self.job, TrackJob):
                result: Result = self._runner.run_tracks(self.job)
            else:
                result = self._runner.run(self.job)
        except Cancelled:
            self.signals.cancelled.emit()
        except Exception as exc:  # noqa: BLE001 - the window reports, it does not crash
            if self._runner.is_cancelled():
                self.signals.cancelled.emit()
            else:
                self.signals.failed.emit(str(exc))
        else:
            self.signals.finished.emit(result)

    def _on_progress(self, event: ProgressEvent) -> None:  # pragma: no cover - worker thread
        self.signals.progress.emit(event)


class DownloadSignals(QtCore.QObject):
    #: component key, 0-100 (or -1 when the size is not known yet)
    progress = QtCore.Signal(str, int)
    #: component key, one line of detail
    detail = QtCore.Signal(str, str)
    #: component key
    finished = QtCore.Signal(str)
    cancelled = QtCore.Signal(str)
    #: component key, error message
    failed = QtCore.Signal(str, str)


class ComponentInstallWorker(QtCore.QRunnable):
    """Downloads and installs one component."""

    def __init__(self, key: str, component=None):
        super().__init__()
        self.key = key
        self.component = component
        self.signals = DownloadSignals()
        self._cancelled = False

    def cancel(self) -> None:
        self._cancelled = True

    def run(self) -> None:  # pragma: no cover - runs on a worker thread
        try:
            manager.install(
                self.key,
                component=self.component,
                on_progress=self._on_progress,
                is_cancelled=lambda: self._cancelled,
            )
        except DownloadCancelled:
            self.signals.cancelled.emit(self.key)
        except PermissionError as exc:
            self.signals.failed.emit(self.key, permission_hint(exc))
        except Exception as exc:  # noqa: BLE001 - the row reports, it does not crash
            self.signals.failed.emit(self.key, str(exc))
        else:
            self.signals.finished.emit(self.key)

    def _on_progress(self, progress: Progress) -> None:  # pragma: no cover - worker thread
        self.signals.progress.emit(self.key, progress.percent)
        self.signals.detail.emit(self.key, format_progress(progress))


class RelocateSignals(QtCore.QObject):
    #: bytes moved, bytes total, current file
    progress = QtCore.Signal(int, int, str)
    #: the folder now in use
    finished = QtCore.Signal(str)
    failed = QtCore.Signal(str)


class RelocateWorker(QtCore.QRunnable):
    """Points the component store at another folder, carrying the files across."""

    def __init__(self, target: Path | None, move_existing: bool = True):
        super().__init__()
        self.target = target
        self.move_existing = move_existing
        self.signals = RelocateSignals()

    def run(self) -> None:  # pragma: no cover - runs on a worker thread
        try:
            location = store.set_data_dir(
                self.target,
                move_existing=self.move_existing,
                on_progress=self._on_progress,
            )
            manager.rebase()
        except Exception as exc:  # noqa: BLE001 - the dialog reports, it does not crash
            self.signals.failed.emit(str(exc))
        else:
            self.signals.finished.emit(str(location))

    def _on_progress(self, moved: int, total: int, detail: str) -> None:  # pragma: no cover
        self.signals.progress.emit(moved, total, detail)


def permission_hint(exc: OSError) -> str:
    """Turn "access denied" into something the user can act on.

    The message Windows gives names a path and nothing else. What is almost
    always happening is a virus scanner holding a freshly downloaded file, and
    the folder it watches hardest is Downloads.
    """

    return (
        f"{exc}\n\n"
        "O Windows negou acesso ao arquivo. Quase sempre é o antivírus segurando "
        "o download que acabou de chegar.\n\n"
        "O que costuma resolver:\n"
        "• Tentar de novo — o download continua de onde parou.\n"
        "• Mover a pasta inteira do programa para fora de Downloads, por exemplo "
        "para C:\\Users\\<seu usuário>\\NishizumiReunioes. É a pasta que o "
        "antivírus vigia mais de perto."
    )


def format_progress(progress: Progress) -> str:
    """One line of download detail: size, speed and time left."""

    parts: list[str] = []
    if progress.total:
        parts.append(f"{human_size(progress.downloaded)} de {human_size(progress.total)}")
    elif progress.downloaded:
        parts.append(human_size(progress.downloaded))
    if progress.speed_bps:
        parts.append(f"{human_size(progress.speed_bps)}/s")
    if progress.eta_seconds:
        parts.append(f"faltam {format_eta(progress.eta_seconds)}")
    if progress.detail and not parts:
        return progress.detail
    if progress.detail:
        parts.append(progress.detail)
    return " · ".join(parts)


def format_eta(seconds: float) -> str:
    total = max(0, int(seconds))
    minutes, secs = divmod(total, 60)
    hours, minutes = divmod(minutes, 60)
    if hours:
        return f"{hours} h {minutes:02d} min"
    if minutes:
        return f"{minutes} min {secs:02d} s"
    return f"{secs} s"


class AnalysisSignals(QtCore.QObject):
    #: (Measurement, Advice) for the recording examined.
    finished = QtCore.Signal(object, object)
    failed = QtCore.Signal(str)


class AnalysisWorker(QtCore.QRunnable):
    """Measures a recording without freezing the window.

    A pass over two hours of audio is quick but not instant, and the window
    has to stay alive while it happens.
    """

    def __init__(self, source: Path):
        super().__init__()
        self.source = source
        self.signals = AnalysisSignals()

    def run(self) -> None:  # pragma: no cover - runs on a worker thread
        from ..analysis import report

        try:
            found, advice = report(self.source)
        except Exception as exc:  # noqa: BLE001 - the dialog reports it
            self.signals.failed.emit(str(exc))
        else:
            self.signals.finished.emit(found, advice)
