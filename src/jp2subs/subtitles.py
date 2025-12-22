"""Subtitle formatting utilities (SRT/VTT/ASS)."""
from __future__ import annotations

from datetime import timedelta
from pathlib import Path
from typing import Iterable, List, Optional

from .models import MasterDocument, Segment

MAX_LINE = 42


def _format_timestamp(seconds: float, sep: str = ",") -> str:
    td = timedelta(seconds=seconds)
    total_seconds = int(td.total_seconds())
    millis = int(round((seconds - total_seconds) * 1000))
    hours, remainder = divmod(total_seconds, 3600)
    minutes, secs = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}{sep}{millis:03d}"


def _wrap_text(text: str, max_len: int = MAX_LINE) -> List[str]:
    words = text.split()
    lines: List[str] = []
    current = ""
    for word in words:
        candidate = f"{current} {word}".strip()
        if len(candidate) <= max_len:
            current = candidate
            continue
        if current:
            lines.append(current)
        current = word
    if current:
        lines.append(current)
    if not lines:
        return [""]
    return lines[:2]


def segment_payload(segment: Segment, primary_lang: str, secondary_lang: Optional[str] = None) -> List[str]:
    primary = segment.translations.get(primary_lang, segment.ja_raw if primary_lang == "ja" else "")
    if not secondary_lang:
        return _wrap_text(primary)

    secondary = segment.translations.get(secondary_lang, segment.ja_raw if secondary_lang == "ja" else "")
    lines = []
    lines.extend(_wrap_text(primary))
    if len(lines) < 2:
        lines.append(secondary)
    else:
        lines[-1] = f"{lines[-1]} / {secondary}"
    return lines[:2]


def render_srt(segments: Iterable[Segment], primary_lang: str, secondary_lang: Optional[str] = None) -> str:
    parts: List[str] = []
    for index, segment in enumerate(segments, start=1):
        start = _format_timestamp(segment.start)
        end = _format_timestamp(segment.end)
        payload = "\n".join(segment_payload(segment, primary_lang, secondary_lang))
        parts.append(f"{index}\n{start} --> {end}\n{payload}\n")
    return "\n".join(parts).strip() + "\n"


def render_vtt(segments: Iterable[Segment], primary_lang: str, secondary_lang: Optional[str] = None) -> str:
    body = render_srt(segments, primary_lang, secondary_lang)
    lines = ["WEBVTT", ""]
    for block in body.strip().split("\n\n"):
        lines.append(block.replace(",", "."))
        lines.append("")
    return "\n".join(lines).strip() + "\n"


def render_ass(segments: Iterable[Segment], primary_lang: str, secondary_lang: Optional[str] = None) -> str:
    header = """[Script Info]
ScriptType: v4.00+
WrapStyle: 2
ScaledBorderAndShadow: yes
YCbCr Matrix: TV.601
[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,Arial,42,&H00FFFFFF,&H000000FF,&H3C000000,&H64000000,0,0,0,0,100,100,0,0,1,2,0,2,20,20,20,1
[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    events: List[str] = []
    for segment in segments:
        start = _format_timestamp(segment.start, sep=".")
        end = _format_timestamp(segment.end, sep=".")
        payload = "\\N".join(segment_payload(segment, primary_lang, secondary_lang))
        events.append(f"Dialogue: 0,{start},{end},Default,,0,0,0,,{payload}")
    return header + "\n".join(events) + "\n"


def write_subtitles(doc: MasterDocument, path: str | Path, fmt: str, lang: str, secondary: Optional[str] = None) -> Path:
    path = Path(path)
    fmt = fmt.lower()
    if fmt == "srt":
        content = render_srt(doc.segments, lang, secondary)
    elif fmt == "vtt":
        content = render_vtt(doc.segments, lang, secondary)
    elif fmt == "ass":
        content = render_ass(doc.segments, lang, secondary)
    else:
        raise ValueError(f"Unsupported subtitle format: {fmt}")
    path.write_text(content, encoding="utf-8")
    return path

