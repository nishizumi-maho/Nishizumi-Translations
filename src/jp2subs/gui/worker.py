"""Background workers for GUI tasks."""
from __future__ import annotations

from pathlib import Path
from typing import List

from .. import asr, audio, romanizer, subtitles, translation, video
from .. import io as io_mod
from ..paths import default_workdir_for_input
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
        self.signals.log.emit("Preparando pipeline...")
        source = self.job.source
        if not source:
            raise RuntimeError("Fonte não definida")
        workdir = self.job.workdir or default_workdir_for_input(source)
        workdir = Path(workdir)
        self.signals.log.emit(f"Workdir: {workdir}")

        audio_path = audio.ingest_media(source, workdir, mono=self.job.mono)
        self._check_cancel()
        doc = asr.transcribe_audio(
            audio_path,
            model_size=self.job.model_size,
            vad_filter=self.job.vad,
            temperature=0.0,
            beam_size=self.job.beam_size,
            device=None,
        )
        master_path = workdir / "master.json"
        subtitles_root: List[Path] = []

        io_mod.save_master(doc, master_path)

        if self.job.generate_romaji:
            doc = romanizer.romanize_segments(doc)
            io_mod.save_master(doc, master_path)

        if self.job.languages:
            doc = translation.translate_document(
                doc,
                target_langs=self.job.languages,
                mode=self.job.translation_mode,
                provider=self.job.translation_provider,
                block_size=20,
                glossary=None,
            )
            io_mod.save_master(doc, master_path)

        for lang in self.job.languages or ["ja"]:
            output_path = workdir / f"subs_{lang}.{self.job.fmt}"
            subtitles.write_subtitles(doc, output_path, self.job.fmt, lang=lang, secondary=self.job.bilingual)
            subtitles_root.append(output_path)
            self.signals.log.emit(f"Exportado: {output_path}")

        self.signals.results.emit(subtitles_root)

    def _check_cancel(self):  # pragma: no cover - GUI thread
        if self._cancelled:
            raise RuntimeError("Job cancelado")


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
            raise RuntimeError("Vídeo ou legenda ausente")
        out_dir = self.job.out_dir or self.job.video.parent
        if self.job.mode == "sidecar":
            out = video.build_out_path(self.job.video, self.job.subtitle, out_dir, True, None, None, mode="sidecar")
            result = video.copy_sidecar(self.job.video, self.job.subtitle, out)
        elif self.job.mode == "softcode":
            out = video.build_out_path(self.job.video, self.job.subtitle, out_dir, True, None, "mkv", mode="softcode")
            result = video.run_ffmpeg_mux_soft(self.job.video, self.job.subtitle, out, container="mkv")
        else:
            out = video.build_out_path(self.job.video, self.job.subtitle, out_dir, True, None, "mp4", mode="hardcode")
            result = video.run_ffmpeg_burn(
                self.job.video, self.job.subtitle, out, codec=self.job.codec, crf=self.job.crf, preset="slow"
            )
        self.signals.results.emit([Path(result)])


class WorkerSignals(QtCore.QObject if QtCore else object):  # type: ignore[misc]
    if QtCore:  # pragma: no cover - type guarded
        finished = QtCore.Signal()
        failed = QtCore.Signal(str)
        progress = QtCore.Signal(str)
        results = QtCore.Signal(list)
        log = QtCore.Signal(str)
    else:  # pragma: no cover - no Qt
        pass

