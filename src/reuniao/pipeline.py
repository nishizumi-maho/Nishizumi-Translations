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

from . import cache, cleanup, diarize, media, transcribe, writers
from .config import Settings
from .model import Transcript, assign_names
from .progress import ProgressEvent, stage_percent
from .speakers import build_utterances, consolidate_speakers, merge_runs


class Cancelled(RuntimeError):
    """The user asked to stop."""


@dataclass
class Job:
    """What to transcribe, and with which preferences."""

    source: Path
    settings: Settings
    output_dir: Path | None = None


@dataclass
class TrackJob:
    """One meeting recorded as several files, one per participant.

    Worth having because it removes the hardest guess in the whole pipeline.
    With a track per person there is nothing to tell apart: whoever is audible
    on track three is the person track three belongs to. No clustering, no
    splinter speakers, and cross-talk stops swallowing words, because each
    voice was recorded on its own.
    """

    sources: list[Path]
    settings: Settings
    output_dir: Path | None = None
    #: Display name per track. Missing ones fall back to the file name.
    names: list[str] = field(default_factory=list)


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

    def run_tracks(self, job: TrackJob) -> Result:
        """Transcribe one meeting recorded as one file per participant."""

        settings = job.settings
        sources = [Path(item) for item in job.sources]
        if not sources:
            raise ValueError("Nenhuma faixa foi informada.")
        missing = [item for item in sources if not item.exists()]
        if missing:
            raise FileNotFoundError(f"Faixa não encontrada: {missing[0]}")

        output_dir = Path(job.output_dir) if job.output_dir else sources[0].parent
        output_dir.mkdir(parents=True, exist_ok=True)
        notes: list[str] = []
        turns: list = []
        duration = 0.0
        model = settings.model or _best_installed_model()
        self._log(f"Modelo: {model} · {len(sources)} faixas")

        for index, source in enumerate(sources):
            self._check()
            share_start = index / len(sources)
            self._emit(
                "Preparar",
                share_start,
                f"Faixa {index + 1} de {len(sources)}: {source.name}",
                "",
            )
            duration = max(duration, media.probe_duration(source))
            audio_path = media.prepare_audio(
                source,
                output_dir,
                level=settings.level_audio,
                dynamic=settings.dynamic_level,
                register_subprocess=self._register,
            )
            try:
                segments = self._transcribe(source, audio_path, model, settings, duration)
                if settings.filter_repetitions:
                    segments, _dropped = cleanup.drop_repeated_segments(segments)
                # No diarization: the file the sound came from is the speaker.
                for piece in build_utterances(segments, [], merge=False):
                    piece.speaker = index
                    turns.append(piece)
            finally:
                audio_path.unlink(missing_ok=True)
            self._log(f"Faixa {index + 1} ({source.name}): {len(segments)} trechos.")

        self._emit("Interlocutores", 1.0, "Cada faixa é um interlocutor.", "")
        turns.sort(key=lambda item: (item.start, item.end))
        merged = merge_runs(turns, merge_gap=settings.merge_gap, max_block=settings.max_block)
        merged, collapsed, corrected = cleanup.tidy_utterances(
            merged, glossary=settings.glossary, collapse_loops=settings.filter_repetitions
        )
        fine, _c, _r = cleanup.tidy_utterances(
            list(turns), glossary=settings.glossary, collapse_loops=settings.filter_repetitions
        )
        if corrected:
            notes.append(f"{corrected} palavras foram ajustadas pelo glossário.")
        notes.append(
            f"Uma faixa por participante ({len(sources)}): os interlocutores vêm dos "
            "arquivos, não de separação de vozes."
        )

        names = [
            (job.names[index].strip() if index < len(job.names) and job.names[index].strip() else source.stem)
            for index, source in enumerate(sources)
        ]
        transcript = Transcript(
            source=str(sources[0]),
            duration=duration or (merged[-1].end if merged else 0.0),
            utterances=merged,
            cues=fine,
            speaker_names=names,
            model=model,
            diarized=True,
            notes=notes,
        )
        files = self._write(transcript, output_dir, sources[0], settings)
        self._emit("Salvar", 1.0, "Transcrição concluída.", files[0].name if files else "")
        return Result(transcript=transcript, files=files, output_dir=output_dir)

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
        audio_path = media.prepare_audio(
            source,
            output_dir,
            level=settings.level_audio,
            dynamic=settings.dynamic_level,
            register_subprocess=self._register,
        )
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
            segments = self._transcribe(source, audio_path, model, settings, duration)
            self._check()
            if not segments:
                notes.append("Nenhuma fala foi reconhecida no áudio.")
            self._log(f"{len(segments)} trechos transcritos.")

            if settings.filter_repetitions:
                segments, looped = cleanup.drop_repeated_segments(segments)
                if looped:
                    note = f"{looped} trechos repetidos em sequência foram descartados."
                    notes.append(note)
                    self._log(note)

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
            # Split first, tidy the speakers, and only then glue the blocks:
            # merging before the splinters are folded away would preserve the
            # very breaks that stop neighbouring turns from joining.
            fine = build_utterances(segments, spans, merge=False)
            if diarized:
                fine, absorbed = consolidate_speakers(fine)
                if absorbed:
                    note = f"{absorbed} falas soltas foram atribuídas a quem falava em volta."
                    notes.append(note)
                    self._log(note)
            merged = merge_runs(fine, merge_gap=settings.merge_gap, max_block=settings.max_block)

            merged, collapsed, corrected = cleanup.tidy_utterances(
                merged,
                glossary=settings.glossary,
                collapse_loops=settings.filter_repetitions,
            )
            # The subtitle exports get the same treatment, so the two files
            # never disagree about what was said.
            fine, _collapsed, _corrected = cleanup.tidy_utterances(
                fine,
                glossary=settings.glossary,
                collapse_loops=settings.filter_repetitions,
            )
            if collapsed:
                note = f"{collapsed} repetições em sequência foram encurtadas."
                notes.append(note)
                self._log(note)
            if corrected:
                note = f"{corrected} palavras foram ajustadas pelo glossário."
                notes.append(note)
                self._log(note)

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

    def _transcribe(self, source: Path, audio_path: Path, model: str, settings, duration: float):
        """Recognise the speech, or reuse the recognition of an earlier run."""

        if settings.reuse_transcription:
            saved = cache.load(source, settings)
            if saved:
                self._log(f"Reaproveitando a transcrição salva ({len(saved)} trechos).")
                self._emit(
                    "Transcrever", 1.0, "Transcrição reaproveitada.", "de uma execução anterior"
                )
                return saved

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
            hotwords=" ".join(settings.glossary),
            avoid_repetition=settings.avoid_repetition,
            threads=settings.threads,
            compute_type=settings.compute_type,
            duration=duration,
            on_progress=self.on_progress,
            is_cancelled=self.is_cancelled,
        )
        # Saved before anything else can fail, which is the whole point.
        if settings.reuse_transcription and segments:
            cache.save(source, settings, segments)
        return segments

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
        files = [
            writers.write_txt(
                transcript,
                text_path,
                layout=settings.layout,
                mark_uncertain=settings.mark_uncertain,
                talk_time=settings.show_talk_time,
            )
        ]
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
