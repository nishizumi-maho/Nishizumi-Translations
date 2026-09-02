"""The shapes the pipeline passes around."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any

#: Fallback label when a voice has no name from the user.
SPEAKER_LABEL = "Interlocutor {number}"


@dataclass
class Word:
    """One word with its own timing, as Whisper reports it."""

    start: float
    end: float
    text: str


@dataclass
class Segment:
    """A stretch of speech straight from Whisper, before speakers are known."""

    start: float
    end: float
    text: str
    words: list[Word] = field(default_factory=list)


@dataclass
class SpeakerSpan:
    """A stretch of audio the diarizer attributed to one voice."""

    start: float
    end: float
    #: 0-based, already renumbered in order of first appearance.
    speaker: int


@dataclass
class Utterance:
    """One turn in the finished transcript: who spoke, when, and what."""

    start: float
    end: float
    text: str
    #: ``None`` when speakers were not identified.
    speaker: int | None = None

    @property
    def duration(self) -> float:
        return max(0.0, self.end - self.start)


@dataclass
class Transcript:
    """The finished job, and everything the writers need to describe it."""

    source: str
    duration: float
    utterances: list[Utterance] = field(default_factory=list)
    #: The same speech before neighbouring turns were joined. Subtitle exports
    #: use it, because a 40-second block reads fine on a page and badly on screen.
    cues: list[Utterance] = field(default_factory=list)
    #: Display names indexed by speaker number; generated when the user gave none.
    speaker_names: list[str] = field(default_factory=list)
    model: str = ""
    language: str = "pt"
    created_at: str = field(default_factory=lambda: datetime.now().isoformat(timespec="seconds"))
    diarized: bool = False
    notes: list[str] = field(default_factory=list)

    @property
    def speaker_count(self) -> int:
        return len({item.speaker for item in self.utterances if item.speaker is not None})

    def name_for(self, speaker: int | None) -> str:
        """Display name for a speaker number, falling back to a generic label."""

        if speaker is None:
            return ""
        if 0 <= speaker < len(self.speaker_names) and self.speaker_names[speaker]:
            return self.speaker_names[speaker]
        return SPEAKER_LABEL.format(number=speaker + 1)

    def to_dict(self) -> dict[str, Any]:
        return {
            "fonte": self.source,
            "duracao": round(self.duration, 3),
            "idioma": self.language,
            "modelo": self.model,
            "criado_em": self.created_at,
            "interlocutores_identificados": self.diarized,
            "interlocutores": [self.name_for(index) for index in range(len(self.speaker_names))],
            "observacoes": list(self.notes),
            "falas": [
                {
                    "inicio": round(item.start, 3),
                    "fim": round(item.end, 3),
                    "interlocutor": self.name_for(item.speaker),
                    "texto": item.text,
                }
                for item in self.utterances
            ],
        }


def assign_names(count: int, names: list[str] | None) -> list[str]:
    """Pad the user's names out to *count* entries, generating the rest."""

    given = list(names or [])
    result: list[str] = []
    for index in range(max(count, 0)):
        name = given[index].strip() if index < len(given) and given[index] else ""
        result.append(name or SPEAKER_LABEL.format(number=index + 1))
    return result


def as_dict(item: Any) -> dict[str, Any]:
    return asdict(item)
