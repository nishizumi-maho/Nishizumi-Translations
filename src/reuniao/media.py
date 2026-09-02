"""Turning whatever the user dropped in into audio both engines can read.

Whisper and the diarizer both want 16 kHz mono, so one FFmpeg pass produces a
single WAV that serves them both. FFmpeg itself comes from the shared
component store, so nothing has to be on ``PATH``.
"""
from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Callable

from jp2subs.config import detect_ffmpeg, detect_ffprobe

#: The sample rate Whisper and the speaker models are both trained on.
SAMPLE_RATE = 16000

AUDIO_SUFFIXES = {".flac", ".mp3", ".wav", ".m4a", ".mka", ".ogg", ".opus", ".aac", ".wma", ".amr"}
VIDEO_SUFFIXES = {".mp4", ".mkv", ".webm", ".mov", ".avi", ".m4v", ".wmv", ".flv"}
MEDIA_SUFFIXES = AUDIO_SUFFIXES | VIDEO_SUFFIXES


class MediaError(RuntimeError):
    """FFmpeg is missing, or it refused the file."""


def is_media(path: str | Path) -> bool:
    return Path(path).suffix.lower() in MEDIA_SUFFIXES


def ffmpeg_binary() -> str:
    found = detect_ffmpeg(None)
    if not found:
        raise MediaError(
            "O FFmpeg não foi encontrado. Instale-o pela página Componentes do aplicativo."
        )
    return found


def probe_duration(path: str | Path) -> float:
    """Length of the recording in seconds, or 0.0 when ffprobe cannot say."""

    ffprobe = detect_ffprobe(None)
    if not ffprobe:
        return 0.0
    command = [
        ffprobe,
        "-v",
        "error",
        "-show_entries",
        "format=duration",
        "-of",
        "default=noprint_wrappers=1:nokey=1",
        str(path),
    ]
    try:
        result = subprocess.run(command, capture_output=True, text=True, check=True)
        return float(result.stdout.strip())
    except (OSError, ValueError, subprocess.SubprocessError):
        return 0.0


def prepare_audio(
    source: str | Path,
    workdir: str | Path,
    *,
    register_subprocess: Callable[[subprocess.Popen], None] | None = None,
) -> Path:
    """Decode *source* to a 16 kHz mono WAV inside *workdir* and return it."""

    source = Path(source)
    if not source.exists():
        raise MediaError(f"Arquivo não encontrado: {source}")

    workdir = Path(workdir)
    workdir.mkdir(parents=True, exist_ok=True)
    target = workdir / "audio16k.wav"

    command = [
        ffmpeg_binary(),
        "-y",
        "-i",
        str(source),
        "-vn",
        "-ac",
        "1",
        "-ar",
        str(SAMPLE_RATE),
        "-c:a",
        "pcm_s16le",
        str(target),
    ]
    process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if register_subprocess:
        register_subprocess(process)
    _stdout, stderr = process.communicate()
    if process.returncode != 0:
        raise MediaError(f"O FFmpeg não conseguiu ler o arquivo.\n{_tail(stderr)}")
    if not target.exists() or target.stat().st_size <= 44:  # 44 bytes = header only
        raise MediaError("O arquivo não tem nenhuma faixa de áudio utilizável.")
    return target


def read_wav_mono(path: str | Path):
    """Load a 16 kHz mono WAV as a float32 numpy array in ``[-1, 1]``."""

    import wave

    import numpy as np

    with wave.open(str(path), "rb") as handle:
        if handle.getsampwidth() != 2:
            raise MediaError("O áudio preparado deveria ser PCM de 16 bits.")
        channels = handle.getnchannels()
        frames = handle.readframes(handle.getnframes())
        rate = handle.getframerate()

    samples = np.frombuffer(frames, dtype=np.int16).astype(np.float32) / 32768.0
    if channels > 1:  # defensive: prepare_audio already downmixes
        samples = samples.reshape(-1, channels).mean(axis=1)
    if rate != SAMPLE_RATE:
        raise MediaError(f"O áudio preparado está a {rate} Hz, e não a {SAMPLE_RATE} Hz.")
    return samples


def _tail(text: str | None, lines: int = 6) -> str:
    content = (text or "").strip().splitlines()
    return "\n".join(content[-lines:])
