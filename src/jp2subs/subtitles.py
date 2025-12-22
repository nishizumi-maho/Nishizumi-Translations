"""Subtitle formatting utilities (SRT/VTT/ASS)."""
from __future__ import annotations

from datetime import timedelta
from pathlib import Path
from typing import Callable, Iterable, List, Optional

from .progress import ProgressEvent, stage_percent

from .models import MasterDocument, Segment

MAX_CHARS_PER_LINE = 42
MAX_LINES = 2


def _format_timestamp(seconds: float, sep: str = ",") -> str:
    td = timedelta(seconds=seconds)
    total_seconds = int(td.total_seconds())
    millis = int(round((seconds - total_seconds) * 1000))
    hours, remainder = divmod(total_seconds, 3600)
    minutes, secs = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}{sep}{millis:03d}"


def _is_cjk_text(text: str, lang: Optional[str]) -> bool:
    if lang == "ja":
        return True
    if not text:
        return False
    cjk_chars = sum(1 for ch in text if "\u3000" <= ch <= "\u9fff" or "\uff66" <= ch <= "\uff9d")
    return (cjk_chars / len(text)) >= 0.4


def _wrap_text(
    text: str,
    *,
    max_chars_per_line: int = MAX_CHARS_PER_LINE,
    max_lines: int = MAX_LINES,
    lang: Optional[str] = None,
) -> List[str]:
    if _is_cjk_text(text, lang):
        punctuation = set("、。！？!?.…")
        lines: List[str] = []
        current = ""
        for ch in text:
            current += ch
            if len(current) >= max_chars_per_line:
                lines.append(current)
                current = ""
                if len(lines) >= max_lines:
                    break
                continue
            if ch in punctuation and len(current) >= max_chars_per_line * 0.6:
                lines.append(current)
                current = ""
                if len(lines) >= max_lines:
                    break
        if len(lines) < max_lines and current:
            lines.append(current)
        if not lines:
            return [""]
        return lines[:max_lines]

    words = text.split()
    lines = []
    current = ""
    for word in words:
        candidate = f"{current} {word}".strip()
        if len(candidate) <= max_chars_per_line:
            current = candidate
            continue
        if current:
            lines.append(current)
            if len(lines) >= max_lines:
                return lines[:max_lines]
        current = word
    if current:
        lines.append(current)
    if not lines:
        return [""]
    return lines[:max_lines]


def segment_payload(
    segment: Segment,
    primary_lang: str,
    secondary_lang: Optional[str] = None,
    *,
    max_chars_per_line: int = MAX_CHARS_PER_LINE,
    max_lines: int = MAX_LINES,
) -> List[str]:
    primary = segment.translations.get(primary_lang, segment.ja_raw if primary_lang == "ja" else "")
    if not secondary_lang:
        return _wrap_text(primary, max_chars_per_line=max_chars_per_line, max_lines=max_lines, lang=primary_lang)

    secondary = segment.translations.get(secondary_lang, segment.ja_raw if secondary_lang == "ja" else "")

    primary_lines = _wrap_text(primary, max_chars_per_line=max_chars_per_line, max_lines=1, lang=primary_lang)
    secondary_lines = _wrap_text(secondary, max_chars_per_line=max_chars_per_line, max_lines=1, lang=secondary_lang)
    lines = [secondary_lines[0] if secondary_lines else "", primary_lines[0] if primary_lines else ""]
    return lines[:max_lines]


def render_srt(
    segments: Iterable[Segment],
    primary_lang: str,
    secondary_lang: Optional[str] = None,
    *,
    max_chars_per_line: int = MAX_CHARS_PER_LINE,
    max_lines: int = MAX_LINES,
) -> str:
    parts: List[str] = []
    for index, segment in enumerate(segments, start=1):
        start = _format_timestamp(segment.start)
        end = _format_timestamp(segment.end)
        payload = "\n".join(
            segment_payload(
                segment,
                primary_lang,
                secondary_lang,
                max_chars_per_line=max_chars_per_line,
                max_lines=max_lines,
            )
        )
        parts.append(f"{index}\n{start} --> {end}\n{payload}\n")
    return "\n".join(parts).strip() + "\n"


def render_vtt(
    segments: Iterable[Segment],
    primary_lang: str,
    secondary_lang: Optional[str] = None,
    *,
    max_chars_per_line: int = MAX_CHARS_PER_LINE,
    max_lines: int = MAX_LINES,
) -> str:
    body = render_srt(
        segments,
        primary_lang,
        secondary_lang,
        max_chars_per_line=max_chars_per_line,
        max_lines=max_lines,
    )
    lines = ["WEBVTT", ""]
    for block in body.strip().split("\n\n"):
        lines.append(block.replace(",", "."))
        lines.append("")
    return "\n".join(lines).strip() + "\n"


def render_ass(
    segments: Iterable[Segment],
    primary_lang: str,
    secondary_lang: Optional[str] = None,
    *,
    max_chars_per_line: int = MAX_CHARS_PER_LINE,
    max_lines: int = MAX_LINES,
) -> str:
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
        payload = "\\N".join(
            segment_payload(
                segment,
                primary_lang,
                secondary_lang,
                max_chars_per_line=max_chars_per_line,
                max_lines=max_lines,
            )
        )
        events.append(f"Dialogue: 0,{start},{end},Default,,0,0,0,,{payload}")
    return header + "\n".join(events) + "\n"


def write_subtitles(
    doc: MasterDocument,
    path: str | Path,
    fmt: str,
    lang: str,
    secondary: Optional[str] = None,
    *,
    max_chars_per_line: int = MAX_CHARS_PER_LINE,
    max_lines: int = MAX_LINES,
    on_progress: Callable[[ProgressEvent], None] | None = None,
) -> Path:
    path = Path(path)
    fmt = fmt.lower()
    if fmt == "srt":
        content = render_srt(
            doc.segments,
            lang,
            secondary,
            max_chars_per_line=max_chars_per_line,
            max_lines=max_lines,
        )
    elif fmt == "vtt":
        content = render_vtt(
            doc.segments,
            lang,
            secondary,
            max_chars_per_line=max_chars_per_line,
            max_lines=max_lines,
        )
    elif fmt == "ass":
        content = render_ass(
            doc.segments,
            lang,
            secondary,
            max_chars_per_line=max_chars_per_line,
            max_lines=max_lines,
        )
    else:
        raise ValueError(f"Unsupported subtitle format: {fmt}")
    if on_progress:
        on_progress(
            ProgressEvent(
                stage="Export",
                percent=stage_percent("Export", 1),
                message="Exportando...",
                detail=f"Escrevendo {path.name}",
            )
        )
    path.write_text(content, encoding="utf-8")
    return path

