"""Which language the recording is in, and what to tell the recogniser about it.

Whisper handles around a hundred languages, and pinning the right one is worth
more than it sounds: told the language, the model stops spending its first
seconds deciding, and stops drifting into a neighbouring one halfway through a
noisy passage.

The app itself stays in Portuguese. This is only about the speech.
"""
from __future__ import annotations

from dataclasses import dataclass

#: Asking Whisper to work the language out for itself.
AUTO = ""


@dataclass(frozen=True)
class Language:
    """One language the recogniser can be pointed at."""

    code: str
    label: str
    #: Written in the language itself, because a prompt in another one only
    #: confuses the model about what it is listening to.
    prompt: str = ""


#: Offered in the menu, most likely first. Any other Whisper code can be typed.
PRESETS: tuple[Language, ...] = (
    Language(
        "pt",
        "Português do Brasil",
        "Transcrição de uma reunião de trabalho em português do Brasil, "
        "com pontuação, acentuação e letras maiúsculas corretas.",
    ),
    Language(
        "en",
        "Inglês",
        "Transcript of a work meeting in English, with correct punctuation "
        "and capitalisation.",
    ),
    Language(
        "es",
        "Espanhol",
        "Transcripción de una reunión de trabajo en español, con puntuación, "
        "acentuación y mayúsculas correctas.",
    ),
    Language(
        "zh",
        "Chinês",
        "一场工作会议的中文记录，标点正确。",
    ),
    Language(AUTO, "Detectar automaticamente", ""),
)

_BY_CODE = {item.code: item for item in PRESETS}


def normalize(code: str) -> str:
    """Tidy what the user typed into something Whisper accepts.

    Regional tags are the common mistake: Whisper knows ``pt``, not ``pt-BR``,
    and rejects the long form rather than falling back to the base language.
    """

    cleaned = (code or "").strip().lower().replace("_", "-")
    if not cleaned or cleaned in {"auto", "automatico", "automático"}:
        return AUTO
    return cleaned.split("-", 1)[0]


def label_for(code: str) -> str:
    """A name for the header of the transcript."""

    normalized = normalize(code)
    known = _BY_CODE.get(normalized)
    if known:
        return known.label
    return f"código {normalized}" if normalized else "detectado automaticamente"


def prompt_for(code: str) -> str:
    """The default context sentence, in the language being transcribed.

    Empty for anything unknown: a prompt in the wrong language is worse than
    none, because the model treats it as an example of what it is hearing.
    """

    known = _BY_CODE.get(normalize(code))
    return known.prompt if known else ""


def is_preset(code: str) -> bool:
    return normalize(code) in _BY_CODE
