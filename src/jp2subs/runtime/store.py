"""Filesystem layout for downloaded components.

Large payloads (multi-gigabyte Whisper models, ffmpeg, CUDA libraries) live in
the machine-local data directory rather than the roaming config directory, so
they never get synced across a domain profile.
"""
from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

ENV_DATA_DIR = "JP2SUBS_DATA_DIR"


def data_dir() -> Path:
    """Root directory for everything jp2subs downloads."""

    override = os.environ.get(ENV_DATA_DIR)
    if override:
        return Path(override).expanduser()

    if sys.platform.startswith("win"):
        base = os.environ.get("LOCALAPPDATA") or os.environ.get("APPDATA")
        if base:
            return Path(base) / "jp2subs"
        return Path.home() / "AppData" / "Local" / "jp2subs"

    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "jp2subs"

    xdg = os.environ.get("XDG_DATA_HOME")
    if xdg:
        return Path(xdg) / "jp2subs"
    return Path.home() / ".local" / "share" / "jp2subs"


def models_dir() -> Path:
    return data_dir() / "models"


def tools_dir() -> Path:
    return data_dir() / "tools"


def cache_dir() -> Path:
    return data_dir() / "cache"


def manifest_path() -> Path:
    return data_dir() / "components.json"


def ensure_dirs() -> None:
    for path in (data_dir(), models_dir(), tools_dir(), cache_dir()):
        path.mkdir(parents=True, exist_ok=True)


def dir_size(path: Path) -> int:
    """Total size in bytes of a file or directory tree. Missing paths are 0."""

    path = Path(path)
    if not path.exists():
        return 0
    if path.is_file():
        return path.stat().st_size
    total = 0
    for item in path.rglob("*"):
        try:
            if item.is_file():
                total += item.stat().st_size
        except OSError:  # pragma: no cover - race with antivirus/cleanup
            continue
    return total


def free_space(path: Path | None = None) -> int:
    """Bytes available on the volume holding ``path`` (defaults to the data dir)."""

    target = Path(path) if path else data_dir()
    while not target.exists() and target.parent != target:
        target = target.parent
    try:
        return shutil.disk_usage(target).free
    except OSError:  # pragma: no cover - unusual filesystems
        return 0


def human_size(num_bytes: float | None) -> str:
    """Format a byte count the way a download dialog should show it."""

    if not num_bytes or num_bytes < 0:
        return "—"
    value = float(num_bytes)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if value < 1024 or unit == "TB":
            if unit == "B":
                return f"{int(value)} {unit}"
            return f"{value:.1f} {unit}"
        value /= 1024
    return f"{value:.1f} TB"  # pragma: no cover - unreachable


def remove_path(path: Path) -> None:
    """Delete a file or directory tree, tolerating partial failures."""

    path = Path(path)
    if not path.exists():
        return
    if path.is_file():
        path.unlink()
        return
    shutil.rmtree(path, ignore_errors=True)
