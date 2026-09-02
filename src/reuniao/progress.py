"""Progress events, and the share of the bar each stage owns."""
from __future__ import annotations

from dataclasses import dataclass

#: Stage name -> (start, end) percentage of the overall run.
STAGE_RANGES: dict[str, tuple[int, int]] = {
    "Preparar": (0, 5),
    "Transcrever": (5, 72),
    "Interlocutores": (72, 94),
    "Salvar": (94, 100),
}

STAGES = tuple(STAGE_RANGES)


@dataclass
class ProgressEvent:
    """One update, shaped for direct display in the UI."""

    stage: str
    percent: int
    message: str
    detail: str = ""


def clamp01(value: float) -> float:
    return max(0.0, min(1.0, value))


def stage_percent(stage: str, fraction: float) -> int:
    start, end = STAGE_RANGES.get(stage, (0, 100))
    return int(start + (end - start) * clamp01(fraction))


def format_clock(seconds: float) -> str:
    """``01:02:03`` for anything an hour or longer, ``02:03`` below that."""

    total = max(0, int(seconds))
    hours, remainder = divmod(total, 3600)
    minutes, secs = divmod(remainder, 60)
    if hours:
        return f"{hours:02d}:{minutes:02d}:{secs:02d}"
    return f"{minutes:02d}:{secs:02d}"


def format_stamp(seconds: float) -> str:
    """Always ``hh:mm:ss`` — what the transcript itself uses."""

    total = max(0, int(seconds))
    hours, remainder = divmod(total, 3600)
    minutes, secs = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}"


def format_duration_pt(seconds: float) -> str:
    """A duration in words, for the transcript header."""

    total = max(0, int(round(seconds)))
    hours, remainder = divmod(total, 3600)
    minutes, secs = divmod(remainder, 60)
    parts = []
    if hours:
        parts.append(f"{hours} h")
    if minutes:
        parts.append(f"{minutes} min")
    if secs or not parts:
        parts.append(f"{secs} s")
    return " ".join(parts)
