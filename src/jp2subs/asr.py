"""ASR integration using faster-whisper."""
from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Callable, Iterable, List, Optional

from rich.console import Console

from .config import resolve_media_tool
from .models import MasterDocument, Meta, Segment
from .progress import ProgressEvent, format_clock, transcribe_time_percent

console = Console()


def resolve_model_source(model_size: str) -> str:
    """Point faster-whisper at a model the app already downloaded, when we have one.

    Returning an absolute folder keeps transcription fully offline. If the name
    is not one we manage (a custom CTranslate2 folder, say) it passes straight
    through and faster-whisper resolves it as usual.
    """

    try:
        from .runtime.manager import manager
    except Exception:  # pragma: no cover - runtime package always ships with the app
        return model_size
    return manager.resolve_model(model_size)


def transcribe_audio(
    audio_path: str | Path,
    model_size: str = "large-v3",
    vad_filter: bool = True,
    temperature: float = 0.0,
    beam_size: int = 5,
    device: Optional[str] = "auto",
    best_of: int | None = None,
    patience: float | None = None,
    length_penalty: float | None = None,
    word_timestamps: bool = True,
    threads: int | None = None,
    compute_type: str | None = None,
    extra_args: dict[str, object] | None = None,
    *,
    on_progress: Callable[[ProgressEvent], None] | None = None,
    is_cancelled: Callable[[], bool] | None = None,
) -> MasterDocument:
    """Run faster-whisper and return a populated master document."""

    try:
        from faster_whisper import WhisperModel
    except Exception as exc:  # pragma: no cover - optional dependency
        raise RuntimeError(
            "faster-whisper is required for transcription. Install it with "
            "'pip install \"jp2subs[asr]\"', or use the packaged Windows build which bundles it."
        ) from exc

    audio_path = Path(audio_path)
    if on_progress:
        on_progress(
            ProgressEvent(stage="Transcribe", percent=transcribe_time_percent(0, 1), message="Transcribing (ASR)...")
        )
    audio_duration = _probe_duration(audio_path)
    model = _create_model_with_fallback(
        WhisperModel,
        model_size=resolve_model_source(model_size),
        device=device,
        threads=threads,
        compute_type=compute_type,
    )
    asr_kwargs = {
        "language": "ja",
        "vad_filter": vad_filter,
        "temperature": temperature,
        "beam_size": beam_size,
        "word_timestamps": word_timestamps,
    }
    if best_of is not None:
        asr_kwargs["best_of"] = best_of
    if patience is not None:
        asr_kwargs["patience"] = patience
    if length_penalty is not None:
        asr_kwargs["length_penalty"] = length_penalty
    if extra_args:
        asr_kwargs.update(extra_args)
    suppress_tokens = asr_kwargs.get("suppress_tokens")
    if isinstance(suppress_tokens, int):
        if suppress_tokens < 0:
            asr_kwargs.pop("suppress_tokens", None)
        else:
            asr_kwargs["suppress_tokens"] = [suppress_tokens]
    segments_iter, info = model.transcribe(
        str(audio_path),
        **asr_kwargs,
    )

    segments: List[Segment] = []
    word_count = 0
    for i, segment in enumerate(_iter_segments(segments_iter), start=1):
        if is_cancelled and is_cancelled():
            raise RuntimeError("Job cancelled")

        words = segment.get("words") or []
        word_count += len(words)
        last_end_time = float(segment["end"])
        detail_parts = [
            f"Time: {format_clock(last_end_time)} / {format_clock(audio_duration)}",
            f"Segments: {i}",
        ]
        if words:
            detail_parts.append(f"Words: {word_count}")
        segments.append(
            Segment(
                id=i,
                start=float(segment["start"]),
                end=last_end_time,
                ja_raw=str(segment["text"]).strip(),
                translations={},
            )
        )
        if on_progress:
            on_progress(
                ProgressEvent(
                    stage="Transcribe",
                    percent=transcribe_time_percent(last_end_time, audio_duration),
                    message="Transcribing (ASR)...",
                    detail=" | ".join(detail_parts),
                )
            )

    meta = Meta(
        source=str(audio_path),
        tool_versions={"faster_whisper": getattr(model, "_model_size", model_size)},
        settings={"vad_filter": str(vad_filter), "temperature": str(temperature), "beam_size": str(beam_size)},
    )
    return MasterDocument(meta=meta, segments=segments)


def _activate_gpu_libraries() -> None:
    """Add the app-managed cuBLAS/cuDNN folder to the DLL search path."""

    try:
        from .runtime.manager import manager
    except Exception:  # pragma: no cover - runtime package always ships with the app
        return
    manager.activate_cuda()


def _create_model_with_fallback(
    WhisperModel, *, model_size: str, device: Optional[str], threads: int | None = None, compute_type: str | None = None
):
    normalized_device = (device or "auto").lower()

    def _build(target: str):
        kwargs = {}
        if threads:
            kwargs["cpu_threads"] = threads
        effective_compute = compute_type
        if target == "cpu" and effective_compute in {"float16", "int8_float16"}:
            # CPU kernels have no float16 path; picking int8 keeps the run alive.
            console.print(f"compute_type='{effective_compute}' is GPU-only; using 'int8' on CPU")
            effective_compute = "int8"
        if effective_compute:
            kwargs["compute_type"] = effective_compute
        return WhisperModel(model_size, device=target, **kwargs)

    if normalized_device in {"auto", "cuda"}:
        _activate_gpu_libraries()

    if normalized_device == "auto":
        try:
            console.print("ASR device: cuda")
            return _build("cuda")
        except Exception as exc:  # noqa: BLE001
            console.print(f"CUDA unavailable or failed: {exc}\nFalling back to CPU")
            console.print("ASR device: cpu")
            return _build("cpu")

    if normalized_device in {"cuda", "cpu"}:
        console.print(f"ASR device: {normalized_device}")
        try:
            return _build(normalized_device)
        except Exception as exc:  # noqa: BLE001
            raise RuntimeError(f"Failed to initialize ASR with device='{normalized_device}': {exc}") from exc

    raise ValueError("device must be one of: auto, cuda, cpu")


def _iter_segments(segments_iter: Iterable) -> Iterable[dict]:
    for seg in segments_iter:
        yield {"start": seg.start, "end": seg.end, "text": seg.text, "words": getattr(seg, "words", None)}


def _probe_duration(audio_path: Path) -> float:
    cmd = [
        resolve_media_tool("ffprobe"),
        "-v",
        "error",
        "-show_entries",
        "format=duration",
        "-of",
        "default=noprint_wrappers=1:nokey=1",
        str(audio_path),
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        return float(result.stdout.strip())
    except Exception:  # pragma: no cover - optional dependency/ffprobe absence
        return 0.0
