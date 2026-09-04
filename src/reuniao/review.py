"""Reading a finished transcript back, for the Review page.

The page needs the same handful of facts whether the transcript was produced a
second ago or last week, so both paths end up here: one turn per line, with
the timing that lets a click land on the right moment of the recording.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from .model import SPEAKER_LABEL, Transcript, Utterance


@dataclass
class Turn:
    """One line of a transcript, as the review list shows it."""

    start: float
    end: float
    speaker: str
    text: str
    uncertain: bool = False
    #: Which voice this was attributed to. Kept alongside the display name so
    #: a correction can move the turn to another speaker, and a rename can
    #: reach every turn of that voice at once.
    speaker_index: int | None = None
    confidence: float = 1.0


@dataclass
class Review:
    """A transcript plus where its recording is."""

    turns: list[Turn]
    source: Path | None = None
    title: str = ""
    #: Where the transcript itself was read from, when it came off disk.
    path: Path | None = None
    #: Display name per voice, editable here.
    speaker_names: list[str] = field(default_factory=list)
    model: str = ""
    language: str = "pt"
    duration: float = 0.0
    diarized: bool = False
    notes: list[str] = field(default_factory=list)

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


    # -- corrections ------------------------------------------------------

    def rename_speaker(self, index: int, name: str) -> None:
        """Give a voice a real name, everywhere it speaks."""

        while len(self.speaker_names) <= index:
            self.speaker_names.append(SPEAKER_LABEL.format(number=len(self.speaker_names) + 1))
        self.speaker_names[index] = name.strip() or SPEAKER_LABEL.format(number=index + 1)
        self._refresh_labels()

    def reassign(self, turn_index: int, speaker_index: int | None) -> None:
        """Move one line to another voice, when the separation got it wrong."""

        turn = self.turns[turn_index]
        turn.speaker_index = speaker_index
        self._refresh_labels()

    def _refresh_labels(self) -> None:
        for turn in self.turns:
            turn.speaker = self.name_for(turn.speaker_index)

    def name_for(self, index: int | None) -> str:
        if index is None:
            return "Não identificado" if self.diarized else ""
        if 0 <= index < len(self.speaker_names) and self.speaker_names[index]:
            return self.speaker_names[index]
        return SPEAKER_LABEL.format(number=index + 1)

    def talk_time(self) -> list[tuple[int, str, float]]:
        """(index, name, seconds) per voice, longest first — for the editor."""

        seconds: dict[int, float] = {}
        for turn in self.turns:
            if turn.speaker_index is None:
                continue
            seconds[turn.speaker_index] = seconds.get(turn.speaker_index, 0.0) + max(
                0.0, turn.end - turn.start
            )
        rows = [(index, self.name_for(index), value) for index, value in seconds.items()]
        return sorted(rows, key=lambda row: row[2], reverse=True)

    def to_transcript(self) -> Transcript:
        """Rebuild a transcript from the corrected review, ready to write out."""

        return Transcript(
            source=str(self.source) if self.source else self.title,
            duration=self.duration or (self.turns[-1].end if self.turns else 0.0),
            utterances=[
                Utterance(
                    start=turn.start,
                    end=turn.end,
                    text=turn.text,
                    speaker=turn.speaker_index,
                    confidence=turn.confidence,
                    weight=max(1, len(turn.text.split())),
                )
                for turn in self.turns
            ],
            speaker_names=list(self.speaker_names),
            model=self.model,
            language=self.language,
            diarized=self.diarized,
            notes=list(self.notes),
        )

def from_transcript(transcript: Transcript) -> Review:
    """Build the review of a run that just finished."""

    turns = [
        Turn(
            start=item.start,
            end=item.end,
            speaker=transcript.name_for(item.speaker),
            text=item.text,
            uncertain=item.uncertain,
            speaker_index=item.speaker,
            confidence=item.confidence,
        )
        for item in transcript.utterances
    ]
    source = Path(transcript.source) if transcript.source else None
    return Review(
        turns=turns,
        source=source,
        title=source.name if source else "",
        speaker_names=list(transcript.speaker_names),
        model=transcript.model,
        language=transcript.language,
        duration=transcript.duration,
        diarized=transcript.diarized,
        notes=list(transcript.notes),
    )


def from_json(path: str | Path) -> Review:
    """Read one of the .json files this app writes."""

    path = Path(path)
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or "falas" not in payload:
        raise ValueError("Este arquivo não é uma transcrição do Nishizumi Reuniões.")

    names = [str(name) for name in (payload.get("interlocutores") or [])]
    by_name = {name: index for index, name in enumerate(names)}

    turns: list[Turn] = []
    for raw in payload.get("falas") or []:
        try:
            speaker = str(raw.get("interlocutor") or "")
            turns.append(
                Turn(
                    start=float(raw["inicio"]),
                    end=float(raw["fim"]),
                    speaker=speaker,
                    text=str(raw.get("texto") or ""),
                    uncertain=bool(raw.get("duvidoso", False)),
                    speaker_index=by_name.get(speaker),
                    confidence=float(raw.get("confianca", 1.0)),
                )
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError("A transcrição está incompleta ou foi editada à mão.") from exc

    source = _find_recording(payload.get("fonte"), path)
    return Review(
        turns=turns,
        source=source,
        title=Path(str(payload.get("fonte") or path)).name,
        path=path,
        speaker_names=names,
        model=str(payload.get("modelo") or ""),
        language=str(payload.get("idioma") or "pt"),
        duration=float(payload.get("duracao") or 0.0),
        diarized=bool(payload.get("interlocutores_identificados", False)),
        notes=[str(note) for note in (payload.get("observacoes") or [])],
    )


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


def save(review: Review, *, layout: str = "blocos") -> list[Path]:
    """Write the corrected transcript back over the files it came from.

    Overwriting is the point: these are corrections to a transcript the user
    is holding, not a new run. Only the formats that exist are rewritten, so
    correcting a name does not scatter new files around their folder.
    """

    from . import writers

    if not review.path:
        raise ValueError("Esta transcrição não veio de um arquivo, então não há o que regravar.")

    transcript = review.to_transcript()
    written: list[Path] = []

    json_path = review.path
    written.append(writers.write_json(transcript, json_path))

    stem = json_path.with_suffix("")
    for suffix, writer in (
        (".txt", lambda path: writers.write_txt(transcript, path, layout=layout)),
        (".srt", lambda path: writers.write_srt(transcript, path)),
        (".vtt", lambda path: writers.write_vtt(transcript, path)),
    ):
        candidate = stem.with_suffix(suffix)
        if candidate.exists():
            written.append(writer(candidate))
    return written
