"""FFmpeg-based muxing and burning helpers."""
from __future__ import annotations

import subprocess
from pathlib import Path

from .audio import run_command


def mux_soft(video: str | Path, subs: str | Path, out_path: str | Path) -> Path:
    cmd = [
        "ffmpeg",
        "-y",
        "-i",
        str(video),
        "-i",
        str(subs),
        "-c",
        "copy",
        "-map",
        "0",
        "-map",
        "1",
        str(out_path),
    ]
    run_command(cmd, "ffmpeg mux")
    return Path(out_path)


def burn_subs(video: str | Path, subs: str | Path, out_path: str | Path, codec: str = "libx264", crf: int = 18) -> Path:
    cmd = [
        "ffmpeg",
        "-y",
        "-i",
        str(video),
        "-vf",
        f"ass={subs}",
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

