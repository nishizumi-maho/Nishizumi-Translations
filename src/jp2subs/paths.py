"""Path sanitization helpers shared by CLI and GUI."""
from __future__ import annotations

from pathlib import Path


def strip_quotes(raw: str) -> str:
    cleaned = raw.strip().strip("\"").strip("'")
    return cleaned


def normalize_input_path(raw: str) -> Path:
    return Path(strip_quotes(raw)).expanduser()


def default_workdir_for_input(path: Path) -> Path:
    return path.parent / "_jobs" / path.stem


def coerce_workdir(path: str | Path) -> Path:
    candidate = Path(path)
    if candidate.suffix:
        return candidate.parent / candidate.stem
    return candidate

