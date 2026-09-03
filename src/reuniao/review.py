"""Reading a finished transcript back, for the Review page.

The page needs the same handful of facts whether the transcript was produced a
second ago or last week, so both paths end up here: one turn per line, with
the timing that lets a click land on the right moment of the recording.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from .model import Transcript


@dataclass
class Turn:
    """One line of a transcript, as the review list shows it."""

    start: float
    end: float
    speaker: str
    text: str
    uncertain: bool = False


@dataclass
class Review:
    """A transcript plus where its recording is."""

    turns: list[Turn]
    source: Path | None = None
    title: str = ""
    #: Where the transcript itself was read from, when it came off disk.
    path: Path | None = None

    @property
    def has_audio(self) -> bool:
        return bool(self.source and self.source.exists())

    def turn_at(self, seconds: float) -> int | None:
        """Index of the turn covering *seconds*, or the one just before it."""

        found = None
        for index, turn in enumerate(self.turns):
            if turn.start > seconds:
                break
            found = index
        if found is None:
            return None
        # Past the end of a turn and before the next one starts, nothing is
        # being said; keeping the last turn highlighted reads better than
        # blanking the list every time somebody pauses.
        return found


def from_transcript(transcript: Transcript) -> Review:
    """Build the review of a run that just finished."""

    turns = [
        Turn(
            start=item.start,
            end=item.end,
            speaker=transcript.name_for(item.speaker),
            text=item.text,
            uncertain=item.uncertain,
        )
        for item in transcript.utterances
    ]
    source = Path(transcript.source) if transcript.source else None
    return Review(turns=turns, source=source, title=source.name if source else "")


def from_json(path: str | Path) -> Review:
    """Read one of the .json files this app writes."""

    path = Path(path)
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or "falas" not in payload:
        raise ValueError("Este arquivo não é uma transcrição do Nishizumi Reuniões.")

    turns: list[Turn] = []
    for raw in payload.get("falas") or []:
        try:
            turns.append(
                Turn(
                    start=float(raw["inicio"]),
                    end=float(raw["fim"]),
                    speaker=str(raw.get("interlocutor") or ""),
                    text=str(raw.get("texto") or ""),
                    uncertain=bool(raw.get("duvidoso", False)),
                )
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError("A transcrição está incompleta ou foi editada à mão.") from exc

    source = _find_recording(payload.get("fonte"), path)
    return Review(turns=turns, source=source, title=Path(str(payload.get("fonte") or path)).name, path=path)


def _find_recording(recorded: object, transcript_path: Path) -> Path | None:
    """Locate the recording, allowing for it having moved since the run.

    The path stored in the file is where it was transcribed. People move
    folders and swap machines, so the folder holding the transcript is checked
    too — that is where the recording usually sits.
    """

    if not recorded:
        return None
    original = Path(str(recorded))
    if original.exists():
        return original
    beside = transcript_path.parent / original.name
    return beside if beside.exists() else None
