"""Saved preferences for the meeting transcriber.

Plain JSON in the user's config folder. Unknown keys are ignored and missing
ones fall back to the defaults, so a file written by an older build still
loads after an upgrade.
"""
from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path
from typing import Any

from . import languages
from .branding import APP_ID

#: Nudges Whisper towards written Brazilian Portuguese: accents, punctuation
#: and capital letters. Without it the first lines often come out unpunctuated.
DEFAULT_PROMPT = (
    "Transcrição de uma reunião de trabalho em português do Brasil, "
    "com pontuação, acentuação e letras maiúsculas corretas."
)

#: How the .txt is laid out. Both keep the timings; they differ in shape.
LAYOUTS = ("blocos", "linhas")

#: Audio treatments, in the order the menu lists them.
TREATMENTS: tuple[tuple[str, str], ...] = (
    ("auto", "Automático (medir a gravação e decidir)"),
    ("equalizar", "Sempre equalizar o volume"),
    ("nivelar", "Equalizar e nivelar as vozes distantes"),
    ("nenhum", "Não tratar o áudio"),
)
TREATMENT_CODES = tuple(code for code, _label in TREATMENTS)


def config_dir() -> Path:
    """Where the settings file lives, following the platform convention.

    In portable mode it moves next to the program instead, so a machine that
    refuses writes to the user profile is not a problem.
    """

    from .portable import config_dir as portable_config_dir, is_active

    if is_active():
        return portable_config_dir()

    appdata = os.environ.get("APPDATA")
    if appdata:
        return Path(appdata) / APP_ID
    xdg = os.environ.get("XDG_CONFIG_HOME")
    if xdg:
        return Path(xdg) / APP_ID
    return Path.home() / ".config" / APP_ID


def config_path() -> Path:
    return config_dir() / "config.json"


@dataclass
class Settings:
    """Everything the Transcribe page remembers between runs."""

    #: Empty means "whichever installed model is best".
    model: str = ""
    #: Whisper language code. Empty asks it to detect the language itself.
    language: str = "pt"
    device: str = "auto"
    #: Eight rather than the usual five: the model weighs more hypotheses per
    #: stretch before committing. Costs roughly a third more time.
    beam_size: int = 8
    vad: bool = True
    #: How the audio is treated before recognition. "auto" measures the
    #: recording and applies what the measurement calls for, which is what
    #: anyone expects from a button that analyses the audio.
    audio_treatment: str = "auto"
    #: Resolved from ``audio_treatment``; kept so an explicit choice survives
    #: a restart and so the cache can see what was actually applied.
    level_audio: bool = True
    #: Also even it out *within* the recording, for a room where people sit at
    #: very different distances from the microphone. Off by default: it lifts
    #: the background along with the quiet voices, and lifted background is
    #: what Whisper hallucinates over.
    dynamic_level: bool = False
    #: Restarts Whisper's context each window, which stops runaway repetition
    #: on long recordings at the cost of a little cross-sentence context.
    avoid_repetition: bool = True
    #: Empty means "use the sentence that belongs to the chosen language".
    initial_prompt: str = ""
    threads: int = 0
    compute_type: str = ""

    #: The queue is one meeting with a track per person, not several meetings.
    tracks_are_speakers: bool = False
    identify_speakers: bool = True
    #: Real names, in the order each voice first speaks. Anything missing keeps
    #: the generic "Interlocutor N" label.
    speaker_names: list[str] = field(default_factory=list)
    #: How readily two stretches of speech count as the same person. The number
    #: of people is found from this rather than stated up front — see diarize.py.
    clustering_threshold: float = 0.5

    #: Names, acronyms and jargon worth spelling right. Fed to the recogniser
    #: as hints, and used to repair near-misses afterwards.
    glossary: list[str] = field(default_factory=list)
    #: Flag turns the recogniser was unsure about with [?].
    mark_uncertain: bool = True
    #: Flag turns spoken over somebody else, where attribution is least sure.
    mark_overlap: bool = True
    #: Sound and a taskbar nudge when a long run finishes.
    notify_when_done: bool = True
    #: Collapse the phrase loops Whisper falls into on long recordings.
    filter_repetitions: bool = True
    #: Reuse a saved raw transcription instead of transcribing again.
    reuse_transcription: bool = True
    #: Talk time per speaker in the transcript header.
    show_talk_time: bool = True

    layout: str = "blocos"
    #: Consecutive lines from the same person are joined while the silence
    #: between them stays under this, up to ``max_block`` seconds in total.
    #: Three seconds, not one: on a real 2h38 meeting, 157 neighbouring turns
    #: belonged to the same person and the median gap between them was two
    #: seconds, so a 1.2 s window joined barely a third of them.
    merge_gap: float = 3.0
    max_block: float = 40.0
    also_srt: bool = False
    also_vtt: bool = False
    #: On by default: it is what lets the Review page reopen a past run.
    also_json: bool = True
    output_dir: str = ""

    theme: str = "dark"
    open_when_done: bool = True

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Settings":
        allowed = {item.name for item in fields(cls)}
        clean = {key: value for key, value in (data or {}).items() if key in allowed}
        settings = cls(**clean)
        settings.normalize()
        return settings

    def normalize(self) -> None:
        """Pull hand-edited or stale values back into range."""

        if self.layout not in LAYOUTS:
            self.layout = "blocos"
        if self.audio_treatment not in TREATMENT_CODES:
            self.audio_treatment = "auto"
        if self.device not in {"auto", "cuda", "cpu"}:
            self.device = "auto"
        self.beam_size = max(1, min(20, int(self.beam_size)))
        self.threads = max(0, min(128, int(self.threads)))
        self.clustering_threshold = max(0.1, min(1.5, float(self.clustering_threshold)))
        self.merge_gap = max(0.0, min(10.0, float(self.merge_gap)))
        self.max_block = max(5.0, min(600.0, float(self.max_block)))
        self.speaker_names = [str(name).strip() for name in self.speaker_names if str(name).strip()]
        self.glossary = [str(term).strip() for term in self.glossary if str(term).strip()]
        self.language = languages.normalize(self.language)
        # A prompt that is simply one of the built-in sentences is not a
        # customisation, and keeping it would pin an old language's wording
        # onto a new language.
        if self.initial_prompt.strip() in {item.prompt for item in languages.PRESETS if item.prompt}:
            self.initial_prompt = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def load_settings(path: Path | None = None) -> Settings:
    target = path or config_path()
    try:
        raw = target.read_text(encoding="utf-8")
    except OSError:
        return Settings()
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:  # hand-edited or half-written file
        return Settings()
    return Settings.from_dict(data if isinstance(data, dict) else {})


def save_settings(settings: Settings, path: Path | None = None) -> Path:
    target = path or config_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    settings.normalize()
    target.write_text(
        json.dumps(settings.to_dict(), indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    return target


def effective_prompt(settings: "Settings") -> str:
    """The context sentence actually sent, custom or the language's own."""

    return settings.initial_prompt.strip() or languages.prompt_for(settings.language)


def parse_glossary(raw: str) -> list[str]:
    """One term per line, blank lines ignored."""

    return [line.strip() for line in str(raw or "").splitlines() if line.strip()]


def parse_speaker_names(raw: str) -> list[str]:
    """Split the "Ana, João, Carla" field into a list, dropping the blanks."""

    separators = ";\n"
    text = str(raw or "")
    for char in separators:
        text = text.replace(char, ",")
    return [part.strip() for part in text.split(",") if part.strip()]
