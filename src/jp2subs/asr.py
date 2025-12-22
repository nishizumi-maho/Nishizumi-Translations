"""ASR integration using faster-whisper."""
from __future__ import annotations

from pathlib import Path
from typing import Iterable, List, Optional

from rich.console import Console

from .models import MasterDocument, Meta, Segment

console = Console()


def transcribe_audio(
    audio_path: str | Path,
    model_size: str = "large-v3",
    vad_filter: bool = True,
    temperature: float = 0.0,
    beam_size: int = 5,
    device: Optional[str] = None,
) -> MasterDocument:
    """Run faster-whisper and return a populated master document."""

    try:
        from faster_whisper import WhisperModel
    except Exception as exc:  # pragma: no cover - optional dependency
        raise RuntimeError(
            "faster-whisper is required for transcription. Install with 'pip install jp2subs[asr]'"
        ) from exc

    audio_path = Path(audio_path)
    model = WhisperModel(model_size, device=device)
    segments_iter, info = model.transcribe(
        str(audio_path),
        language="ja",
        vad_filter=vad_filter,
        temperature=temperature,
        beam_size=beam_size,
        word_timestamps=True,
    )

    segments: List[Segment] = []
    for i, segment in enumerate(_iter_segments(segments_iter), start=1):
        segments.append(
            Segment(
                id=i,
                start=float(segment["start"]),
                end=float(segment["end"]),
                ja_raw=str(segment["text"]).strip(),
                translations={},
            )
        )

    meta = Meta(
        source=str(audio_path),
        tool_versions={"faster_whisper": getattr(model, "_model_size", model_size)},
        settings={"vad_filter": str(vad_filter), "temperature": str(temperature), "beam_size": str(beam_size)},
    )
    return MasterDocument(meta=meta, segments=segments)


def _iter_segments(segments_iter: Iterable) -> Iterable[dict]:
    for seg in segments_iter:
        yield {"start": seg.start, "end": seg.end, "text": seg.text}

