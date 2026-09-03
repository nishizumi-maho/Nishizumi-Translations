"""Whisper transcription, pinned to Brazilian Portuguese.

Only the knobs that matter for a meeting recording are exposed; everything
else is left at faster-whisper's own defaults, including its temperature
fallback, which is what pulls a long recording out of a repetition loop.
"""
from __future__ import annotations

from pathlib import Path
from typing import Callable, Iterable

from .model import Segment, Word
from .progress import ProgressEvent, format_clock, stage_percent

#: Whisper's own code for Portuguese. It covers pt-BR; there is no separate one.
LANGUAGE = "pt"

#: Voice detection tuned for one recorder in a room rather than a headset.
#: The library already pads each chunk by 400 ms; what it does not do by
#: default is expect half the room to be far from the microphone, and at the
#: stock threshold of 0.5 their quieter speech is thrown away as silence
#: before the recogniser ever sees it.
VAD_OPTIONS = {"threshold": 0.45, "speech_pad_ms": 600}


class TranscriptionError(RuntimeError):
    """faster-whisper is unavailable, or the model could not be loaded."""


def resolve_model(name: str) -> str:
    """Turn a model name into a folder the app already downloaded, if it has one."""

    try:
        from jp2subs.runtime.manager import manager
    except Exception:  # pragma: no cover - the runtime always ships with the app
        return name
    return manager.resolve_model(name)


def transcribe(
    audio_path: str | Path,
    *,
    model: str = "large-v3-turbo",
    device: str = "auto",
    beam_size: int = 5,
    vad: bool = True,
    initial_prompt: str = "",
    hotwords: str = "",
    avoid_repetition: bool = True,
    threads: int = 0,
    compute_type: str = "",
    duration: float = 0.0,
    on_progress: Callable[[ProgressEvent], None] | None = None,
    is_cancelled: Callable[[], bool] | None = None,
) -> list[Segment]:
    """Run Whisper over *audio_path* and return its segments, words included."""

    try:
        from faster_whisper import WhisperModel
    except Exception as exc:  # pragma: no cover - optional dependency
        raise TranscriptionError(
            "O faster-whisper não está instalado. Use o aplicativo empacotado, ou "
            'instale com: pip install "reuniao[asr]"'
        ) from exc

    audio_path = Path(audio_path)
    _emit(on_progress, 0.0, "Carregando o modelo...", "")

    engine = _load_model(WhisperModel, resolve_model(model), device, threads, compute_type)

    segments_iter, info = engine.transcribe(
        str(audio_path),
        language=LANGUAGE,
        task="transcribe",
        beam_size=beam_size,
        vad_filter=vad,
        vad_parameters=dict(VAD_OPTIONS) if vad else None,
        word_timestamps=True,
        initial_prompt=initial_prompt or None,
        # Names and acronyms the model would otherwise spell its own way. This
        # is a nudge, not a rule: it raises their odds, it does not force them.
        hotwords=hotwords or None,
        condition_on_previous_text=not avoid_repetition,
    )
    total = duration or float(getattr(info, "duration", 0.0) or 0.0)

    segments: list[Segment] = []
    words_seen = 0
    for segment in segments_iter:
        if is_cancelled and is_cancelled():
            raise TranscriptionError("Transcrição cancelada.")
        text = str(segment.text or "").strip()
        words = list(_words_of(segment))
        words_seen += len(words)
        if not text:
            continue
        segments.append(
            Segment(
                start=float(segment.start),
                end=float(segment.end),
                text=text,
                words=words,
                confidence=_segment_confidence(segment, words),
            )
        )
        _emit(
            on_progress,
            (float(segment.end) / total) if total else 0.0,
            "Transcrevendo a reunião...",
            f"{format_clock(float(segment.end))} de {format_clock(total)} · "
            f"{len(segments)} falas · {words_seen} palavras",
        )

    _emit(on_progress, 1.0, "Transcrição concluída.", f"{len(segments)} falas")
    return segments


def _words_of(segment) -> Iterable[Word]:
    for word in getattr(segment, "words", None) or []:
        text = getattr(word, "word", "")
        if not str(text).strip():
            continue
        yield Word(
            start=float(word.start),
            end=float(word.end),
            text=str(text),
            confidence=_clamp(getattr(word, "probability", 1.0)),
        )


def _segment_confidence(segment, words: list[Word]) -> float:
    """How sure Whisper was about this stretch, on a 0..1 scale.

    Word probabilities are the honest measure when they are there. Without
    them the average log-probability stands in: it is unbounded below, and
    around -1.0 is where a segment stops being trustworthy, so that is where
    the mapping puts zero.
    """

    if words:
        return _clamp(sum(word.confidence for word in words) / len(words))
    logprob = getattr(segment, "avg_logprob", None)
    if logprob is None:
        return 1.0
    return _clamp(1.0 + float(logprob))


def _clamp(value) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):  # pragma: no cover - defensive
        return 1.0
    return max(0.0, min(1.0, number))


def _load_model(WhisperModel, source: str, device: str, threads: int, compute_type: str):
    """Build the model, dropping from GPU to CPU when CUDA is not usable."""

    wanted = (device or "auto").lower()
    if wanted not in {"auto", "cuda", "cpu"}:
        raise TranscriptionError("O dispositivo deve ser auto, cuda ou cpu.")

    if wanted in {"auto", "cuda"}:
        _activate_gpu_libraries()

    def build(target: str):
        options: dict[str, object] = {}
        if threads:
            options["cpu_threads"] = threads
        effective = compute_type
        if target == "cpu" and effective in {"float16", "int8_float16"}:
            effective = "int8"  # there is no float16 kernel on CPU
        if effective:
            options["compute_type"] = effective
        return WhisperModel(source, device=target, **options)

    if wanted == "auto":
        try:
            return build("cuda")
        except Exception:  # noqa: BLE001 - any CUDA failure means fall back
            return build("cpu")
    try:
        return build(wanted)
    except Exception as exc:  # noqa: BLE001
        raise TranscriptionError(f"Não foi possível iniciar o modelo em '{wanted}': {exc}") from exc


def _activate_gpu_libraries() -> None:
    try:
        from jp2subs.runtime.manager import manager
    except Exception:  # pragma: no cover - the runtime always ships with the app
        return
    manager.activate_cuda()


def _emit(
    on_progress: Callable[[ProgressEvent], None] | None, fraction: float, message: str, detail: str
) -> None:
    if on_progress:
        on_progress(
            ProgressEvent(
                stage="Transcrever",
                percent=stage_percent("Transcrever", fraction),
                message=message,
                detail=detail,
            )
        )
