"""Keeping the expensive half of the work.

Transcribing an hour of audio is the part that takes an hour. Separating the
voices, writing the files and correcting the spelling all take seconds. When
one of those fails — a full disk, a missing model, a mistyped output folder —
re-running should not mean transcribing the whole meeting again.

So the raw recognition is saved the moment it finishes, keyed by the recording
and by every setting that would change the result. Change the model or the
prompt and the key changes with it, which is what stops a stale transcription
being served for a run that asked for something different.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from jp2subs.runtime import store

from .model import Segment, Word

#: Bumped when the stored shape changes, so old files are ignored rather than
#: misread.
FORMAT = 1


def cache_dir() -> Path:
    return store.data_dir() / "cache" / "transcricoes"


def key_for(source: Path, settings) -> str:
    """A fingerprint of the recording and the settings that shaped the run."""

    source = Path(source)
    try:
        stat = source.stat()
        identity = f"{source.resolve()}|{stat.st_size}|{int(stat.st_mtime)}"
    except OSError:
        identity = str(source)

    shaped = "|".join(
        str(part)
        for part in (
            FORMAT,
            identity,
            settings.model,
            settings.beam_size,
            settings.vad,
            settings.avoid_repetition,
            settings.initial_prompt,
            ",".join(settings.glossary),
        )
    )
    return hashlib.sha1(shaped.encode("utf-8")).hexdigest()


def path_for(source: Path, settings) -> Path:
    return cache_dir() / f"{key_for(source, settings)}.json"


def save(source: Path, settings, segments: list[Segment]) -> Path | None:
    """Store the raw recognition. Returns the file, or None if it could not."""

    target = path_for(source, settings)
    payload = {
        "formato": FORMAT,
        "fonte": str(Path(source)),
        "modelo": settings.model,
        "trechos": [
            {
                "inicio": round(segment.start, 3),
                "fim": round(segment.end, 3),
                "texto": segment.text,
                "confianca": round(segment.confidence, 4),
                "palavras": [
                    [round(word.start, 3), round(word.end, 3), word.text, round(word.confidence, 4)]
                    for word in segment.words
                ],
            }
            for segment in segments
        ],
    }
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    except OSError:
        # A cache that cannot be written is a missed shortcut, not a failure.
        return None
    return target


def load(source: Path, settings) -> list[Segment] | None:
    """The saved recognition for this exact recording and settings, if any."""

    target = path_for(source, settings)
    try:
        payload = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if payload.get("formato") != FORMAT:
        return None

    segments: list[Segment] = []
    for raw in payload.get("trechos", []):
        try:
            words = [
                Word(start=float(item[0]), end=float(item[1]), text=str(item[2]), confidence=float(item[3]))
                for item in raw.get("palavras", [])
            ]
            segments.append(
                Segment(
                    start=float(raw["inicio"]),
                    end=float(raw["fim"]),
                    text=str(raw["texto"]),
                    words=words,
                    confidence=float(raw.get("confianca", 1.0)),
                )
            )
        except (KeyError, TypeError, ValueError, IndexError):
            return None  # a half-written or hand-edited file is not worth trusting
    return segments or None


def forget(source: Path, settings) -> None:
    path_for(source, settings).unlink(missing_ok=True)


def clear() -> int:
    """Delete every stored transcription. Returns how many files went."""

    removed = 0
    for item in cache_dir().glob("*.json"):
        try:
            item.unlink()
            removed += 1
        except OSError:  # pragma: no cover - something else has it open
            continue
    return removed


def stored_size() -> int:
    return sum(item.stat().st_size for item in cache_dir().glob("*.json") if item.is_file())
