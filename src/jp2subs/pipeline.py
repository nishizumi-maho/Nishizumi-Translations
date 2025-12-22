"""Shared pipeline runner for CLI and GUI."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable, List

from . import asr, audio, romanizer, subtitles
from . import io as io_mod
from .config import load_config
from .paths import default_workdir_for_input
from .progress import ProgressEvent, stage_percent


StageCallback = Callable[[str], None]
ProgressCallback = Callable[[ProgressEvent], None]


@dataclass
class PipelineCallbacks:
    on_stage_start: StageCallback | None = None
    on_stage_done: StageCallback | None = None
    on_stage_progress: ProgressCallback | None = None
    on_log: Callable[[str], None] | None = None
    on_error: Callable[[str, Exception], None] | None = None
    on_item_start: Callable[[Path], None] | None = None
    on_item_done: Callable[[Path, List[Path]], None] | None = None


class PipelineRunner:
    """Execute the jp2subs pipeline while emitting structured events."""

    def __init__(self, callbacks: PipelineCallbacks | None = None):
        self.callbacks = callbacks or PipelineCallbacks()
        self._cancelled = False

    def cancel(self) -> None:
        self._cancelled = True

    def run(self, job) -> List[Path]:
        if not job.source:
            raise RuntimeError("Source file missing")
        source = Path(job.source)
        if self.callbacks.on_item_start:
            self.callbacks.on_item_start(source)
        workdir = Path(job.workdir or default_workdir_for_input(source))
        self._log(f"Workdir: {workdir}")
        outputs: List[Path] = []

        try:
            audio_path = self._stage("Ingest", lambda: self._ingest(source, workdir, job))
            doc = self._stage(
                "Transcribe",
                lambda: self._transcribe(audio_path, job),
            )
            master_path = workdir / "master.json"
            io_mod.save_master(doc, master_path)

            if job.generate_romaji:
                doc = self._stage("Romanize", lambda: romanizer.romanize_segments(doc, on_progress=self._emit_progress))
                io_mod.save_master(doc, master_path)

            outputs.extend(
                self._stage(
                    "Export",
                    lambda: self._export(doc, workdir, ["ja"], job.fmt, None),
                )
            )
            if self.callbacks.on_item_done:
                self.callbacks.on_item_done(source, outputs)
            return outputs
        except Exception as exc:  # noqa: BLE001
            if self.callbacks.on_error:
                self.callbacks.on_error("pipeline", exc)
            raise

    def _ingest(self, source: Path, workdir: Path, job) -> Path:
        return audio.ingest_media(
            source,
            workdir,
            mono=job.mono,
            on_progress=self._emit_progress,
        )

    def _transcribe(self, audio_path: Path, job):
        return asr.transcribe_audio(
            audio_path,
            model_size=job.model_size,
            vad_filter=job.vad,
            temperature=0.0,
            beam_size=job.beam_size,
            device="auto",
            best_of=job.best_of,
            patience=job.patience,
            length_penalty=job.length_penalty,
            word_timestamps=job.word_timestamps,
            threads=job.threads,
            compute_type=job.compute_type,
            extra_args=job.extra_asr_args,
            on_progress=self._emit_progress,
            is_cancelled=lambda: self._cancelled,
        )

    def _export(self, doc, workdir: Path, languages: Iterable[str], fmt: str, bilingual: str | None) -> List[Path]:
        subtitles_root: List[Path] = []
        languages = list(languages)
        for index, lang in enumerate(languages, start=1):
            output_path = workdir / f"subs_{lang}.{fmt}"
            progress_fraction = index / max(1, len(languages))
            self._emit_progress(
                ProgressEvent(
                    stage="Export",
                    percent=self._stage_percent("Export", progress_fraction),
                    message="Exporting subtitles...",
                    detail=f"Writing {output_path.name}",
                )
            )
            subtitles.write_subtitles(
                doc,
                output_path,
                fmt,
                lang=lang,
                secondary=bilingual,
            )
            subtitles_root.append(output_path)
            self._log(f"Exported: {output_path}")
        self._emit_progress(
            ProgressEvent(stage="Export", percent=self._stage_percent("Export", 1), message="Export complete")
        )
        return subtitles_root

    def _stage(self, name: str, fn):
        if self.callbacks.on_stage_start:
            self.callbacks.on_stage_start(name)
        self._emit_progress(ProgressEvent(stage=name, percent=self._stage_percent(name, 0), message=f"{name}..."))
        result = fn()
        if self.callbacks.on_stage_done:
            self.callbacks.on_stage_done(name)
        self._emit_progress(ProgressEvent(stage=name, percent=self._stage_percent(name, 1), message=f"{name} done"))
        return result

    def _emit_progress(self, event: ProgressEvent):
        if self.callbacks.on_stage_progress:
            self.callbacks.on_stage_progress(event)

    def _log(self, line: str):
        if self.callbacks.on_log:
            self.callbacks.on_log(line)

    def _stage_percent(self, stage: str, fraction: float) -> int:
        return stage_percent(stage, fraction)

