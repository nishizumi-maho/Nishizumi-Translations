"""Media ingestion helpers for jp2subs."""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from rich.console import Console

from .io import ensure_workdir

console = Console()

SUPPORTED_AUDIO = {"flac", "mp3", "wav", "m4a", "mka"}
SUPPORTED_VIDEO = {"mp4", "mkv", "webm", "mov", "avi"}


def is_audio(path: Path) -> bool:
    return path.suffix.lower().lstrip(".") in SUPPORTED_AUDIO


def is_video(path: Path) -> bool:
    return path.suffix.lower().lstrip(".") in SUPPORTED_VIDEO


def ingest_media(input_path: str | Path, workdir: str | Path, mono: bool = False) -> Path:
    """Copy or extract audio into the working directory.

    Returns the path to the extracted audio file (FLAC 48kHz).
    """

    ensure_workdir(workdir)
    src = Path(input_path)
    if not src.exists():
        raise FileNotFoundError(f"Input {src} not found")

    audio_out = Path(workdir) / "audio.flac"

    if is_audio(src):
        console.log(f"Copying audio to {audio_out}")
        shutil.copy(src, audio_out)
        return audio_out

    if not is_video(src):
        raise ValueError(f"Unsupported media type: {src.suffix}")

    console.log("Extracting audio track with ffmpeg (FLAC 48kHz)...")
    channels = "mono" if mono else "stereo"
    cmd = [
        "ffmpeg",
        "-y",
        "-i",
        str(src),
        "-vn",
        "-acodec",
        "flac",
        "-ar",
        "48000",
        "-ac",
        "1" if mono else "2",
        str(audio_out),
    ]
    run_command(cmd, "ffmpeg audio extraction")
    console.log(f"Audio extracted to {audio_out} ({channels})")
    return audio_out


def run_command(cmd: list[str], title: str) -> None:
    """Run a subprocess and raise on failure."""

    try:
        subprocess.run(cmd, check=True)
    except FileNotFoundError as exc:
        raise RuntimeError(f"{title} failed: binary not found (is it on PATH?)") from exc
    except subprocess.CalledProcessError as exc:
        raise RuntimeError(f"{title} failed with exit code {exc.returncode}") from exc

