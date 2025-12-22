"""Progress reporting helpers."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Tuple

STAGE_RANGES: Dict[str, Tuple[int, int]] = {
    "Ingest": (0, 10),
    "Transcribe": (10, 70),
    "Romanize": (70, 80),
    "Translate": (80, 95),
    "Export": (95, 100),
}


@dataclass
class ProgressEvent:
    """Represents a progress update across the pipeline."""

    stage: str
    percent: int
    message: str
    detail: str | None = None


def clamp01(value: float) -> float:
    return max(0.0, min(1.0, value))


def stage_percent(stage: str, fraction: float) -> int:
    """Map a 0..1 fraction to the absolute percentage for a stage."""

    start, end = STAGE_RANGES.get(stage, (0, 100))
    frac = clamp01(fraction)
    return int(start + (end - start) * frac)


def transcribe_time_percent(last_end_time: float, audio_duration: float) -> int:
    """Progress percent for transcription based on elapsed audio time."""

    fraction = 0.0 if audio_duration <= 0 else clamp01(last_end_time / audio_duration)
    return stage_percent("Transcribe", fraction)


def format_clock(seconds: float) -> str:
    minutes = int(seconds) // 60
    secs = int(seconds) % 60
    return f"{minutes:02d}:{secs:02d}"
