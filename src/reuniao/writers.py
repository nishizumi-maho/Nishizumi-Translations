"""Writing the transcript out.

The .txt is the point of the app; SRT, VTT and JSON are there for when the
recording is going somewhere else afterwards.
"""
from __future__ import annotations

import json
import textwrap
from datetime import datetime
from pathlib import Path

from .model import Transcript, Utterance
from .progress import format_duration_pt, format_stamp

#: Text files are written with a BOM: it is what makes Notepad and Excel on a
#: Brazilian Windows show the accents instead of mojibake.
TEXT_ENCODING = "utf-8-sig"

#: Width the block layout wraps at. Comfortable in Notepad at a default window.
WRAP_COLUMNS = 96

ARROW = "→"
RULE = "─" * 72


def write_txt(transcript: Transcript, path: str | Path, *, layout: str = "blocos") -> Path:
    """Write the readable transcript. ``blocos`` is the subtitle-style default."""

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    body = _blocks(transcript) if layout != "linhas" else _lines(transcript)
    content = "\n".join([*_header(transcript), "", *body, ""])
    path.write_text(content, encoding=TEXT_ENCODING)
    return path


def _header(transcript: Transcript) -> list[str]:
    created = _pretty_datetime(transcript.created_at)
    lines = [
        "TRANSCRIÇÃO DA REUNIÃO",
        RULE,
        f"Arquivo......: {Path(transcript.source).name}",
        f"Duração......: {format_duration_pt(transcript.duration)}",
        f"Gerada em....: {created}",
        f"Modelo.......: {transcript.model or 'desconhecido'} (Whisper)",
        f"Idioma.......: português do Brasil",
    ]
    if transcript.diarized and transcript.speaker_names:
        names = ", ".join(transcript.speaker_names)
        lines.append(f"Interlocutores: {len(transcript.speaker_names)} ({names})")
    else:
        lines.append("Interlocutores: não identificados")
    lines.extend(f"Observação...: {note}" for note in transcript.notes)
    lines.append(RULE)
    return lines


def _blocks(transcript: Transcript) -> list[str]:
    """Timestamp and speaker on their own line, then the speech, wrapped."""

    out: list[str] = []
    for item in transcript.utterances:
        speaker = transcript.name_for(item.speaker)
        head = f"[{format_stamp(item.start)} {ARROW} {format_stamp(item.end)}]"
        out.append(f"{head}  {speaker}" if speaker else head)
        out.extend(textwrap.wrap(item.text, width=WRAP_COLUMNS) or [""])
        out.append("")
    return out


def _lines(transcript: Transcript) -> list[str]:
    """One turn per line, for grepping and diffing."""

    out: list[str] = []
    for item in transcript.utterances:
        speaker = transcript.name_for(item.speaker)
        head = f"[{format_stamp(item.start)} {ARROW} {format_stamp(item.end)}]"
        out.append(f"{head} {speaker}: {item.text}" if speaker else f"{head} {item.text}")
    return out


def write_srt(transcript: Transcript, path: str | Path) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    blocks = []
    for index, item in enumerate(_cues(transcript), start=1):
        start = _timecode(item.start, ",")
        end = _timecode(max(item.end, item.start + 0.2), ",")
        blocks.append(f"{index}\n{start} --> {end}\n{_cue_text(transcript, item)}\n")
    path.write_text("\n".join(blocks), encoding="utf-8")
    return path


def write_vtt(transcript: Transcript, path: str | Path) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    blocks = ["WEBVTT", ""]
    for item in _cues(transcript):
        start = _timecode(item.start, ".")
        end = _timecode(max(item.end, item.start + 0.2), ".")
        blocks.append(f"{start} --> {end}\n{_cue_text(transcript, item)}\n")
    path.write_text("\n".join(blocks), encoding="utf-8")
    return path


def write_json(transcript: Transcript, path: str | Path) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(transcript.to_dict(), indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    return path


def _cues(transcript: Transcript) -> list[Utterance]:
    return transcript.cues or transcript.utterances


def _cue_text(transcript: Transcript, item: Utterance) -> str:
    speaker = transcript.name_for(item.speaker)
    return f"{speaker}: {item.text}" if speaker else item.text


def _timecode(seconds: float, millisecond_separator: str) -> str:
    total = max(0.0, float(seconds))
    hours, remainder = divmod(int(total), 3600)
    minutes, secs = divmod(remainder, 60)
    millis = int(round((total - int(total)) * 1000))
    if millis == 1000:  # rounding up a hair under the next second
        millis, secs = 0, secs + 1
    return f"{hours:02d}:{minutes:02d}:{secs:02d}{millisecond_separator}{millis:03d}"


def _pretty_datetime(stamp: str) -> str:
    try:
        return datetime.fromisoformat(stamp).strftime("%d/%m/%Y às %H:%M")
    except ValueError:  # pragma: no cover - only for hand-edited transcripts
        return stamp
