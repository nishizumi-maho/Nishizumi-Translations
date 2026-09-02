"""One meeting in, one transcript out.

Prepare the audio, transcribe it, work out who was speaking, write the files.
The GUI and the CLI both drive this; neither of them knows what a Whisper
segment looks like.
"""
from __future__ import annotations

import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from . import diarize, media, transcribe, writers
from .config import Settings
from .model import Transcript, assign_names
from .progress import ProgressEvent, stage_percent
from .speakers import build_utterances


class Cancelled(RuntimeError):
    """The user asked to stop."""


@dataclass
class Job:
    """What to transcribe, and with which preferences."""

    source: Path
    settings: Settings
    output_dir: Path | None = None


@dataclass
class Result:
    """What came out: the transcript itself and the files written."""

    transcript: Transcript
    files: list[Path] = field(default_factory=list)
    output_dir: Path | None = None

    @property
    def text_file(self) -> Path | None:
        for item in self.files:
            if item.suffix.lower() == ".txt":
                return item
        return self.files[0] if self.files else None


ProgressCallback = Callable[[ProgressEvent], None]
LogCallback = Callable[[str], None]


class Runner:
    """Runs one job, reporting progress and stopping when asked."""

    def __init__(
        self,
        *,
        on_progress: ProgressCallback | None = None,
        on_log: LogCallback | None = None,
    ):
        self.on_progress = on_progress
        self.on_log = on_log
        self._cancelled = False
        self._process: subprocess.Popen | None = None

    # -- control ----------------------------------------------------------

    def cancel(self) -> None:
        self._cancelled = True
        process = self._process
        if process and process.poll() is None:
            try:
                process.terminate()
            except OSError:  # pragma: no cover - the process already went away
                pass

    def is_cancelled(self) -> bool:
        return self._cancelled

    # -- the run ----------------------------------------------------------

    def run(self, job: Job) -> Result:
        settings = job.settings
        source = Path(job.source)
        if not source.exists():
            raise FileNotFoundError(f"Arquivo não encontrado: {source}")

        output_dir = Path(job.output_dir) if job.output_dir else source.parent
        output_dir.mkdir(parents=True, exist_ok=True)
        notes: list[str] = []

        # -- prepare ------------------------------------------------------
        self._emit("Preparar", 0.0, "Preparando o áudio...", source.name)
        duration = media.probe_duration(source)
        audio_path = media.prepare_audio(source, output_dir, register_subprocess=self._register)
        self._check()
        self._log(f"Áudio preparado: {audio_path.name} ({16} kHz mono)")
        self._emit("Preparar", 1.0, "Áudio pronto.", "")

        try:
            # -- transcribe -----------------------------------------------
            model = settings.model or _best_installed_model()
            self._log(f"Modelo: {model}")
            # The engine reports its own progress as segments come in, but it
            # stays silent until the model is loaded — which on a cold start is
            # the longest wait of the run.
            self._emit("Transcrever", 0.0, "Transcrevendo a reunião...", "Carregando o modelo...")
            segments = transcribe.transcribe(
                audio_path,
                model=model,
                device=settings.device,
                beam_size=settings.beam_size,
                vad=settings.vad,
                initial_prompt=settings.initial_prompt,
                avoid_repetition=settings.avoid_repetition,
                threads=settings.threads,
                compute_type=settings.compute_type,
                duration=duration,
                on_progress=self.on_progress,
                is_cancelled=self.is_cancelled,
            )
            self._check()
            if not segments:
                notes.append("Nenhuma fala foi reconhecida no áudio.")
            self._log(f"{len(segments)} trechos transcritos.")

            # -- speakers -------------------------------------------------
            spans = []
            diarized = False
            if settings.identify_speakers:
                spans, diarized, problem = self._diarize(audio_path, settings)
                if problem:
                    notes.append(problem)
                    self._log(problem)
            else:
                self._emit("Interlocutores", 1.0, "Identificação de interlocutores desligada.", "")

            # -- assemble -------------------------------------------------
            merged = build_utterances(
                segments,
                spans,
                merge_gap=settings.merge_gap,
                max_block=settings.max_block,
            )
            fine = build_utterances(segments, spans, merge=False)
            numbered = [item.speaker for item in merged if item.speaker is not None]
            speaker_count = max(numbered) + 1 if diarized and numbered else 0

            transcript = Transcript(
                source=str(source),
                duration=duration or (merged[-1].end if merged else 0.0),
                utterances=merged,
                cues=fine,
                speaker_names=assign_names(speaker_count, settings.speaker_names),
                model=model,
                diarized=diarized,
                notes=notes,
            )

            # -- write ----------------------------------------------------
            self._check()
            files = self._write(transcript, output_dir, source, settings)
            self._emit("Salvar", 1.0, "Transcrição concluída.", files[0].name if files else "")
        except Cancelled:
            audio_path.unlink(missing_ok=True)
            raise
        else:
            # The 16 kHz copy is only an intermediate, and it costs about
            # 100 MB an hour. It stays put after a failure, so re-running does
            # not have to decode the recording again.
            audio_path.unlink(missing_ok=True)
            return Result(transcript=transcript, files=files, output_dir=output_dir)

    # -- stages -----------------------------------------------------------

    def _diarize(self, audio_path: Path, settings: Settings):
        """Returns (spans, diarized, problem-or-empty-string)."""

        reason = diarize.unavailable_reason()
        if reason:
            self._emit("Interlocutores", 1.0, "Interlocutores não identificados.", "")
            return [], False, reason

        self._emit("Interlocutores", 0.0, "Identificando os interlocutores...", "")
        samples = media.read_wav_mono(audio_path)
        try:
            spans = diarize.diarize(
                samples,
                threshold=settings.clustering_threshold,
                threads=settings.threads,
                on_progress=self.on_progress,
                is_cancelled=self.is_cancelled,
            )
        except diarize.DiarizationUnavailable as exc:
            self._check()  # a cancellation surfaces as this too
            return [], False, str(exc)
        self._check()
        if not spans:
            return [], False, "Nenhuma voz distinta foi encontrada; a transcrição saiu sem interlocutores."
        self._log(f"{len({item.speaker for item in spans})} vozes distintas encontradas.")
        self._emit("Interlocutores", 1.0, "Interlocutores identificados.", "")
        return spans, True, ""

    def _write(self, transcript: Transcript, output_dir: Path, source: Path, settings: Settings) -> list[Path]:
        self._emit("Salvar", 0.2, "Salvando a transcrição...", "")
        # One stem for every format, so the .srt always belongs to the .txt
        # written beside it even when an earlier run is already there.
        text_path = unique_path(output_dir / f"{source.stem}.txt")
        stem = text_path.stem
        files = [writers.write_txt(transcript, text_path, layout=settings.layout)]
        if settings.also_srt:
            files.append(writers.write_srt(transcript, output_dir / f"{stem}.srt"))
        if settings.also_vtt:
            files.append(writers.write_vtt(transcript, output_dir / f"{stem}.vtt"))
        if settings.also_json:
            files.append(writers.write_json(transcript, output_dir / f"{stem}.json"))
        for item in files:
            self._log(f"Salvo: {item}")
        return files

    # -- plumbing ---------------------------------------------------------

    def _register(self, process: subprocess.Popen) -> None:
        self._process = process

    def _check(self) -> None:
        if self._cancelled:
            raise Cancelled("Transcrição cancelada.")

    def _emit(self, stage: str, fraction: float, message: str, detail: str) -> None:
        if self.on_progress:
            self.on_progress(
                ProgressEvent(
                    stage=stage, percent=stage_percent(stage, fraction), message=message, detail=detail
                )
            )

    def _log(self, line: str) -> None:
        if self.on_log:
            self.on_log(line)


def unique_path(path: Path) -> Path:
    """``nome.txt`` if it is free, otherwise ``nome (2).txt`` and so on.

    Transcribing the same recording twice should never quietly destroy the
    first transcript, which may already have been corrected by hand.
    """

    if not path.exists():
        return path
    for index in range(2, 1000):
        candidate = path.with_name(f"{path.stem} ({index}){path.suffix}")
        if not candidate.exists():
            return candidate
    raise FileExistsError(f"Não foi possível encontrar um nome livre para {path}")


def _best_installed_model() -> str:
    from jp2subs.runtime.manager import manager

    return manager.default_model()
