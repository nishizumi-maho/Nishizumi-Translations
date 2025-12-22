"""FFmpeg-based muxing and burning helpers."""
from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Dict, Optional

from .audio import run_command


def _escape_filter_path(path: Path) -> str:
    """Escape a filesystem path for ffmpeg filter arguments."""

    normalized = path.as_posix()
    return (
        normalized.replace("\\", "/")
        .replace(":", r"\:")
        .replace(" ", r"\ ")
    )


def _build_subtitles_filter(
    subs: Path, font: Optional[str], styles: Optional[Dict[str, str]], fonts_dir: Optional[Path]
) -> str:
    base = f"subtitles={_escape_filter_path(subs)}"
    if fonts_dir:
        base += f":fontsdir={_escape_filter_path(fonts_dir)}"

    style_entries: list[str] = []
    if font:
        style_entries.append(f"Fontname={font}")
    for key, value in (styles or {}).items():
        style_entries.append(f"{key}={value}")

    if style_entries:
        force_style = ",".join(style_entries).replace("'", r"\\'")
        base += f":force_style='{force_style}'"
    return base


def mux_soft(video: str | Path, subs: str | Path, out_path: str | Path) -> Path:
    out_suffix = Path(out_path).suffix.lower().lstrip(".")
    subs_suffix = Path(subs).suffix.lower().lstrip(".")

    if out_suffix == "mkv":
        if subs_suffix not in {"ass", "srt"}:
            raise ValueError("MKV soft-mux only supports ASS or SRT subtitles")
        subtitle_codec = "ass" if subs_suffix == "ass" else "srt"
    elif out_suffix == "mp4":
        if subs_suffix == "ass":
            raise ValueError("MP4 container does not support ASS subtitles; export SRT instead")
        if subs_suffix != "srt":
            raise ValueError("MP4 soft-mux only supports SRT subtitles")
        subtitle_codec = "mov_text"
    else:
        raise ValueError(f"Unsupported output container: .{out_suffix}")

    cmd = [
        "ffmpeg",
        "-y",
        "-i",
        str(video),
        "-i",
        str(subs),
        "-c:v",
        "copy",
        "-c:a",
        "copy",
        "-c:s",
        subtitle_codec,
        "-map",
        "0",
        "-map",
        "1",
        str(out_path),
    ]
    run_command(cmd, "ffmpeg mux")
    return Path(out_path)


def burn_subs(
    video: str | Path,
    subs: str | Path,
    out_path: str | Path,
    codec: str = "libx264",
    crf: int = 18,
    font: Optional[str] = None,
    styles: Optional[Dict[str, str]] = None,
    fonts_dir: Optional[Path] = None,
) -> Path:
    subtitles_filter = _build_subtitles_filter(Path(subs), font, styles, fonts_dir)
    cmd = [
        "ffmpeg",
        "-y",
        "-i",
        str(video),
        "-vf",
        subtitles_filter,
        "-c:v",
        codec,
        "-crf",
        str(crf),
        "-preset",
        "slow",
        "-c:a",
        "copy",
        str(out_path),
    ]
    run_command(cmd, "ffmpeg burn")
    return Path(out_path)


def ffmpeg_version() -> str:
    """Return the ffmpeg version string or raise a helpful error."""

    try:
        result = subprocess.run(
            ["ffmpeg", "-version"], check=True, capture_output=True, text=True
        )
    except FileNotFoundError as exc:  # pragma: no cover - exercised via error path tests
        raise RuntimeError("ffmpeg not found on PATH") from exc
    except subprocess.CalledProcessError as exc:  # pragma: no cover - exercised via error path tests
        raise RuntimeError(f"ffmpeg -version failed with exit code {exc.returncode}") from exc

    first_line = result.stdout.splitlines()[0] if result.stdout else "ffmpeg version (unknown)"
    return first_line

