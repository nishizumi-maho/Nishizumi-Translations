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

from .branding import APP_ID

#: Nudges Whisper towards written Brazilian Portuguese: accents, punctuation
#: and capital letters. Without it the first lines often come out unpunctuated.
DEFAULT_PROMPT = (
    "Transcrição de uma reunião de trabalho em português do Brasil, "
    "com pontuação, acentuação e letras maiúsculas corretas."
)

#: How the .txt is laid out. Both keep the timings; they differ in shape.
LAYOUTS = ("blocos", "linhas")


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
    device: str = "auto"
    beam_size: int = 5
    vad: bool = True
    #: Restarts Whisper's context each window, which stops runaway repetition
    #: on long recordings at the cost of a little cross-sentence context.
    avoid_repetition: bool = True
    initial_prompt: str = DEFAULT_PROMPT
    threads: int = 0
    compute_type: str = ""

    identify_speakers: bool = True
    #: Real names, in the order each voice first speaks. Anything missing keeps
    #: the generic "Interlocutor N" label.
    speaker_names: list[str] = field(default_factory=list)
    #: How readily two stretches of speech count as the same person. The number
    #: of people is found from this rather than stated up front — see diarize.py.
    clustering_threshold: float = 0.5

    layout: str = "blocos"
    #: Consecutive lines from the same person are joined while the silence
    #: between them stays under this, up to ``max_block`` seconds in total.
    merge_gap: float = 1.2
    max_block: float = 40.0
    also_srt: bool = False
    also_vtt: bool = False
    also_json: bool = False
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
        if self.device not in {"auto", "cuda", "cpu"}:
            self.device = "auto"
        self.beam_size = max(1, min(20, int(self.beam_size)))
        self.threads = max(0, min(128, int(self.threads)))
        self.clustering_threshold = max(0.1, min(1.5, float(self.clustering_threshold)))
        self.merge_gap = max(0.0, min(10.0, float(self.merge_gap)))
        self.max_block = max(5.0, min(600.0, float(self.max_block)))
        self.speaker_names = [str(name).strip() for name in self.speaker_names if str(name).strip()]

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


def parse_speaker_names(raw: str) -> list[str]:
    """Split the "Ana, João, Carla" field into a list, dropping the blanks."""

    separators = ";\n"
    text = str(raw or "")
    for char in separators:
        text = text.replace(char, ",")
    return [part.strip() for part in text.split(",") if part.strip()]
