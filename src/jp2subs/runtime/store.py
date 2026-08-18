"""Filesystem layout for downloaded components.

Large payloads (multi-gigabyte Whisper models, ffmpeg, CUDA libraries) live in
the machine-local data directory rather than the roaming config directory, so
they never get synced across a domain profile.

The user is not stuck with that default. :func:`set_data_dir` records any
folder they pick — typically a roomier second disk — in a small pointer file
next to ``config.toml``, and every path below follows it. Resolution order is
``JP2SUBS_DATA_DIR`` (for portable runs and tests), then the pointer file,
then the per-platform default.
"""
from __future__ import annotations

import json
import os
import shutil
import sys
from pathlib import Path
from typing import Callable

ENV_DATA_DIR = "JP2SUBS_DATA_DIR"

#: Written next to ``config.toml`` so the Windows installer can seed it too.
LOCATION_FILE = "data_location.json"

#: Reported while a relocation runs: bytes moved, bytes total, current file.
MoveProgress = Callable[[int, int, str], None]

#: Names that mark a folder as ours, so a relocation never adopts a folder
#: full of somebody else's files.
_OWN_MARKERS = ("components.json", "models", "tools", "cache")


def default_data_dir() -> Path:
    """Where downloads land when the user has not chosen anywhere else."""

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


def env_override() -> Path | None:
    """Folder forced by ``JP2SUBS_DATA_DIR``, which outranks the saved choice."""

    override = os.environ.get(ENV_DATA_DIR)
    return Path(override).expanduser() if override else None


def location_file() -> Path:
    """Pointer file holding the folder the user picked."""

    from ..config import app_config_dir  # local import: config may reach back here

    return app_config_dir() / LOCATION_FILE


def configured_data_dir() -> Path | None:
    """The saved custom folder, or ``None`` when the default is in use."""

    try:
        raw = location_file().read_text(encoding="utf-8")
    except OSError:
        return None
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:  # hand-edited or half-written file
        return None
    value = str((data or {}).get("data_dir") or "").strip()
    return Path(value).expanduser() if value else None


def data_dir() -> Path:
    """Root directory for everything jp2subs downloads."""

    return env_override() or configured_data_dir() or default_data_dir()


def is_custom_location() -> bool:
    return data_dir() != default_data_dir()


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


# -- choosing a location ---------------------------------------------------


def looks_like_data_dir(path: Path) -> bool:
    """True when *path* is empty or already holds a jp2subs component tree."""

    path = Path(path)
    if not path.exists():
        return True
    if not path.is_dir():
        return False
    entries = list(path.iterdir())
    if not entries:
        return True
    return any((path / marker).exists() for marker in _OWN_MARKERS)


def validate_location(path: str | Path) -> str:
    """Return an empty string when *path* is usable, otherwise the reason why not.

    Returning a message rather than raising keeps the caller free to show it in
    a dialog, print it, or ignore it.
    """

    raw = str(path).strip()
    if not raw:
        return "Choose a folder for the models and tools."

    target = Path(raw).expanduser()
    if not target.is_absolute():
        return "Use a full path, for example D:\\jp2subs or /mnt/media/jp2subs."
    if target.exists() and not target.is_dir():
        return f"{target} is a file, not a folder."

    # Nesting is checked first: it is the more useful complaint when a folder
    # is both a parent of the current one and full of unrelated files.
    current = data_dir()
    if target != current:
        if _is_within(target, current):
            return "That folder is inside the current one. Pick a folder outside it."
        if _is_within(current, target):
            return "That folder contains the current one. Pick a separate folder."

    if not looks_like_data_dir(target):
        return (
            f"{target} already holds other files. Pick an empty folder — "
            f"{target / 'jp2subs'} works — so removing components never touches them."
        )

    probe = target
    while not probe.exists() and probe.parent != probe:
        probe = probe.parent
    if not os.access(probe, os.W_OK):
        return f"{probe} is not writable. Pick a folder you own."
    return ""


def set_data_dir(
    path: str | Path | None,
    *,
    move_existing: bool = False,
    on_progress: MoveProgress | None = None,
) -> Path:
    """Point jp2subs at *path* (``None`` restores the default folder).

    With ``move_existing`` the components already downloaded travel to the new
    folder first, so the app never loses track of a multi-gigabyte model.
    """

    target = default_data_dir() if path is None else Path(path).expanduser()
    problem = validate_location(target)
    if problem:
        raise ValueError(problem)

    current = data_dir()
    if move_existing and current != target:
        move_data(current, target, on_progress=on_progress)

    pointer = location_file()
    if target == default_data_dir():
        pointer.unlink(missing_ok=True)
    else:
        pointer.parent.mkdir(parents=True, exist_ok=True)
        pointer.write_text(
            json.dumps({"data_dir": str(target)}, indent=2) + "\n", encoding="utf-8"
        )

    ensure_dirs()
    return target


def move_data(source: str | Path, target: str | Path, *, on_progress: MoveProgress | None = None) -> None:
    """Move every downloaded file from *source* into *target*.

    A rename is tried first, which is instant when both folders sit on the same
    drive. Across drives the files go one at a time so the caller can show
    progress; an interrupted move can simply be run again, since files already
    copied are overwritten rather than duplicated.
    """

    source = Path(source)
    target = Path(target)
    if source == target:
        return
    if not source.exists():
        target.mkdir(parents=True, exist_ok=True)
        return

    if _is_empty(target):
        try:
            if target.exists():
                target.rmdir()
            target.parent.mkdir(parents=True, exist_ok=True)
            source.rename(target)
        except OSError:
            pass  # different volume, or something has a file open: copy instead
        else:
            _report(on_progress, 1, 1, "")
            return

    files = [item for item in source.rglob("*") if item.is_file()]
    total = sum(_size_of(item) for item in files)
    moved = 0
    target.mkdir(parents=True, exist_ok=True)

    for item in files:
        relative = item.relative_to(source)
        destination = target / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        if destination.exists():
            destination.unlink()
        size = _size_of(item)
        shutil.move(str(item), str(destination))
        moved += size
        _report(on_progress, moved, total, str(relative))

    shutil.rmtree(source, ignore_errors=True)


def _is_empty(path: Path) -> bool:
    return not path.exists() or (path.is_dir() and not any(path.iterdir()))


def _is_within(path: Path, parent: Path) -> bool:
    try:
        return path.resolve() != parent.resolve() and path.resolve().is_relative_to(parent.resolve())
    except OSError:  # pragma: no cover - unresolvable path
        return False


def _size_of(path: Path) -> int:
    try:
        return path.stat().st_size
    except OSError:  # pragma: no cover - race with antivirus/cleanup
        return 0


def _report(on_progress: MoveProgress | None, moved: int, total: int, detail: str) -> None:
    if on_progress:
        on_progress(moved, total, detail)


# -- inspection ------------------------------------------------------------


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
