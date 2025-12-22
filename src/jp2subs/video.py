"""FFmpeg-based muxing and burning helpers."""
from __future__ import annotations

import subprocess
import shutil
from pathlib import Path
from typing import Dict, Optional

from .audio import run_command


def _normalize_suffix(suffix: str | None) -> str:
    if not suffix:
        return ""
    return suffix if suffix.startswith(".") else f".{suffix}"


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
    ext = subs.suffix.lower().lstrip(".")
    filter_name = "ass" if ext == "ass" else "subtitles"
    base = f"{filter_name}={_escape_filter_path(subs)}"
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


def validate_subtitle_format(container: str, subtitle: str | Path) -> str:
    container = container.lower()
    ext = Path(subtitle).suffix.lower().lstrip(".")

    if container == "mp4":
        if ext == "ass":
            raise ValueError("MP4 não suporta ASS; use MKV ou converta")
        if ext not in {"srt", "vtt"}:
            raise ValueError("MP4 soft-mux only supports SRT or VTT subtitles")
        return "mov_text"

    if container == "mkv":
        if ext not in {"ass", "srt"}:
            raise ValueError("MKV soft-mux only supports ASS or SRT subtitles")
        return "ass" if ext == "ass" else "srt"

    raise ValueError(f"Unsupported output container: .{container}")


def build_out_path(
    video: str | Path,
    subtitle: str | Path,
    out_dir: str | Path | None,
    same_name: bool,
    suffix: str | None,
    container: str | None,
    mode: str,
    out: str | Path | None = None,
) -> Path:
    if out:
        return Path(out)

    video_path = Path(video)
    subtitle_path = Path(subtitle)
    base_dir = Path(out_dir) if out_dir else video_path.parent
    base_name = video_path.stem if same_name else subtitle_path.stem

    if mode == "softcode":
        container_value = (container or "mkv").lower()
        suffix_value = _normalize_suffix(suffix)
        return base_dir / f"{base_name}{suffix_value}.{container_value}"

    if mode == "hardcode":
        suffix_value = _normalize_suffix(suffix if suffix is not None else ".hard")
        return base_dir / f"{base_name}{suffix_value}.mp4"

    if mode == "sidecar":
        return base_dir / f"{base_name}{subtitle_path.suffix}"

    raise ValueError(f"Unknown mode for output build: {mode}")


def run_ffmpeg_mux_soft(
    video: str | Path,
    subtitle: str | Path,
    out_path: str | Path,
    container: str,
    lang: str | None = None,
    verbose: bool = False,
) -> Path:
    subtitle_codec = validate_subtitle_format(container, subtitle)
    cmd = [
        "ffmpeg",
        "-y",
        "-i",
        str(video),
        "-i",
        str(subtitle),
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
    ]

    if lang:
        cmd.extend(["-metadata:s:s:0", f"language={lang}"])

    cmd.append(str(out_path))
    if verbose:
        print("[ffmpeg mux]", " ".join(cmd))
    run_command(cmd, "ffmpeg mux")
    return Path(out_path)


def run_ffmpeg_burn(
    video: str | Path,
    subtitle: str | Path,
    out_path: str | Path,
    codec: str,
    crf: int,
    preset: str,
    font: Optional[str] = None,
    styles: Optional[Dict[str, str]] = None,
    fonts_dir: Optional[Path] = None,
    verbose: bool = False,
) -> Path:
    subtitles_filter = _build_subtitles_filter(Path(subtitle), font, styles, fonts_dir)
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
        preset,
        "-c:a",
        "copy",
        str(out_path),
    ]
    if verbose:
        print("[ffmpeg burn]", " ".join(cmd))
    run_command(cmd, "ffmpeg burn")
    return Path(out_path)


def copy_sidecar(video: str | Path, subtitle: str | Path, out_path: str | Path) -> Path:
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy(subtitle, out_path)
    return out_path


def mux_soft(video: str | Path, subs: str | Path, out_path: str | Path) -> Path:
    out_suffix = Path(out_path).suffix.lower().lstrip(".")
    return run_ffmpeg_mux_soft(video, subs, out_path, container=out_suffix)


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
    return run_ffmpeg_burn(video, subs, out_path, codec=codec, crf=crf, preset="slow", font=font, styles=styles, fonts_dir=fonts_dir)


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

