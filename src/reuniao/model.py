"""The shapes the pipeline passes around."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any

#: Fallback label when a voice has no name from the user.
SPEAKER_LABEL = "Interlocutor {number}"

#: Mean word confidence under which a turn is flagged for a human to check.
#: Whisper is confidently wrong more often than it is unsure, so this catches
#: the mumbled and the drowned-out rather than every mistake.
UNCERTAIN_BELOW = 0.6

#: What a flagged turn is prefixed with in the text file.
UNCERTAIN_MARK = "[?]"

#: Marks a turn recorded while more than one person was talking.
OVERLAP_MARK = "[><]"

#: Shown where speakers were identified but this stretch matched no voice —
#: crosstalk, or someone too far from the microphone.
UNKNOWN_SPEAKER = "Não identificado"


@dataclass
class Word:
    """One word with its own timing, as Whisper reports it."""

    start: float
    end: float
    text: str
    #: How sure Whisper was, 0..1. 1.0 when the engine did not say.
    confidence: float = 1.0


@dataclass
class Segment:
    """A stretch of speech straight from Whisper, before speakers are known."""

    start: float
    end: float
    text: str
    words: list[Word] = field(default_factory=list)
    #: Mean word confidence, 0..1.
    confidence: float = 1.0


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
    #: Mean word confidence over the turn, 0..1.
    confidence: float = 1.0
    #: How many words the confidence was averaged over, so merging two turns
    #: can weight them properly instead of averaging the averages.
    weight: int = 1
    #: Someone else was talking at the same time. Both the words and the name
    #: on them are least reliable here.
    overlapped: bool = False

    @property
    def duration(self) -> float:
        return max(0.0, self.end - self.start)

    @property
    def uncertain(self) -> bool:
        return self.confidence < UNCERTAIN_BELOW


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

    def talk_time(self) -> list[tuple[str, float, float]]:
        """(name, seconds, share) per speaker, longest first.

        Silence and crosstalk mean the shares are of *speech*, not of the
        recording, so they add up to 100% between the people who spoke.
        """

        seconds: dict[int | None, float] = {}
        for item in self.utterances:
            seconds[item.speaker] = seconds.get(item.speaker, 0.0) + item.duration
        total = sum(seconds.values())
        rows = [
            (self.name_for(speaker), value, (value / total) if total else 0.0)
            for speaker, value in seconds.items()
        ]
        return sorted(rows, key=lambda row: row[1], reverse=True)

    @property
    def uncertain_count(self) -> int:
        return sum(1 for item in self.utterances if item.uncertain)

    @property
    def overlapped_count(self) -> int:
        return sum(1 for item in self.utterances if item.overlapped)

    def name_for(self, speaker: int | None) -> str:
        """Display name for a speaker number, falling back to a generic label."""

        if speaker is None:
            # In a transcript with no speakers at all, every turn is unnamed
            # and saying so on each one would be noise. Once the voices *are*
            # separated, a turn nobody could be attributed to is worth naming.
            return UNKNOWN_SPEAKER if self.diarized else ""
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
            "tempo_de_fala": [
                {"interlocutor": name, "segundos": round(seconds, 1), "porcentagem": round(share * 100, 1)}
                for name, seconds, share in self.talk_time()
            ],
            "falas": [
                {
                    "inicio": round(item.start, 3),
                    "fim": round(item.end, 3),
                    "interlocutor": self.name_for(item.speaker),
                    "texto": item.text,
                    "confianca": round(item.confidence, 3),
                    "duvidoso": item.uncertain,
                    "sobreposta": item.overlapped,
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
