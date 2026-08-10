"""Resumable HTTP downloads and archive extraction with progress reporting.

Uses only the standard library so the frozen app never depends on ``requests``
being importable.
"""
from __future__ import annotations

import json
import shutil
import tarfile
import time
import urllib.error
import urllib.request
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Iterable

from .. import __version__

USER_AGENT = f"jp2subs/{__version__} (+https://github.com/nishizumi-maho/Nishizumi-Translations)"
CHUNK_SIZE = 1024 * 512
NETWORK_TIMEOUT = 60


class DownloadCancelled(RuntimeError):
    """Raised when a caller's ``is_cancelled`` callback returns True."""


@dataclass
class Progress:
    """A single progress tick, shaped for direct display in a UI."""

    label: str
    downloaded: int = 0
    total: int = 0
    #: 0-100 for the whole operation, or -1 when the total is unknown.
    percent: int = 0
    speed_bps: float = 0.0
    eta_seconds: float | None = None
    detail: str = ""


ProgressCallback = Callable[[Progress], None]
CancelCheck = Callable[[], bool]


def _request(url: str, *, headers: dict[str, str] | None = None) -> urllib.request.Request:
    merged = {"User-Agent": USER_AGENT, "Accept-Encoding": "identity"}
    if headers:
        merged.update(headers)
    return urllib.request.Request(url, headers=merged)


def fetch_bytes(url: str, *, headers: dict[str, str] | None = None, timeout: int = NETWORK_TIMEOUT) -> bytes:
    with urllib.request.urlopen(_request(url, headers=headers), timeout=timeout) as response:
        return response.read()


def fetch_json(url: str, *, headers: dict[str, str] | None = None, timeout: int = NETWORK_TIMEOUT) -> Any:
    merged = {"Accept": "application/json"}
    if headers:
        merged.update(headers)
    return json.loads(fetch_bytes(url, headers=merged, timeout=timeout).decode("utf-8"))


def post_json(
    url: str,
    payload: Any,
    *,
    headers: dict[str, str] | None = None,
    timeout: int = NETWORK_TIMEOUT,
) -> Any:
    """POST a JSON body and decode the JSON response."""

    body = json.dumps(payload).encode("utf-8")
    merged = {"Content-Type": "application/json", "Accept": "application/json"}
    if headers:
        merged.update(headers)
    request = urllib.request.Request(url, data=body, headers={**{"User-Agent": USER_AGENT}, **merged})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def post_form(
    url: str,
    fields: list[tuple[str, str]],
    *,
    headers: dict[str, str] | None = None,
    timeout: int = NETWORK_TIMEOUT,
) -> Any:
    """POST url-encoded fields, repeating keys where a list is needed."""

    import urllib.parse

    body = urllib.parse.urlencode(fields).encode("utf-8")
    merged = {"Content-Type": "application/x-www-form-urlencoded", "Accept": "application/json"}
    if headers:
        merged.update(headers)
    request = urllib.request.Request(url, data=body, headers={**{"User-Agent": USER_AGENT}, **merged})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def remote_size(url: str, *, timeout: int = NETWORK_TIMEOUT) -> int:
    """Content length for ``url``, or 0 when the server will not say."""

    request = _request(url)
    request.get_method = lambda: "HEAD"  # type: ignore[method-assign]
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return int(response.headers.get("Content-Length") or 0)
    except (urllib.error.URLError, ValueError, OSError):
        return 0


def _check_cancelled(is_cancelled: CancelCheck | None) -> None:
    if is_cancelled and is_cancelled():
        raise DownloadCancelled("Cancelled by user")


def download_file(
    url: str,
    dest: Path,
    *,
    label: str | None = None,
    on_progress: ProgressCallback | None = None,
    is_cancelled: CancelCheck | None = None,
    resume: bool = True,
    expected_size: int = 0,
    base_downloaded: int = 0,
    base_total: int = 0,
) -> Path:
    """Download ``url`` to ``dest``, resuming a previous partial attempt.

    ``base_downloaded``/``base_total`` let a caller fold this file into a
    larger multi-file operation so the reported percentage covers the whole set.
    """

    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    part = dest.with_suffix(dest.suffix + ".part")
    display = label or dest.name

    already = part.stat().st_size if (resume and part.exists()) else 0
    if not resume and part.exists():
        part.unlink()

    headers: dict[str, str] = {}
    if already:
        headers["Range"] = f"bytes={already}-"

    _check_cancelled(is_cancelled)

    try:
        response = urllib.request.urlopen(_request(url, headers=headers), timeout=NETWORK_TIMEOUT)
    except urllib.error.HTTPError as exc:
        if already and exc.code in (416, 501):
            # Server refused the range; start over from scratch.
            part.unlink(missing_ok=True)
            return download_file(
                url,
                dest,
                label=label,
                on_progress=on_progress,
                is_cancelled=is_cancelled,
                resume=False,
                expected_size=expected_size,
                base_downloaded=base_downloaded,
                base_total=base_total,
            )
        raise

    with response:
        if already and response.status != 206:
            # Range ignored: rewrite from the beginning.
            already = 0
            part.unlink(missing_ok=True)

        remaining = int(response.headers.get("Content-Length") or 0)
        total = already + remaining if remaining else expected_size
        overall_total = base_total or total
        mode = "ab" if already else "wb"
        downloaded = already
        started = time.monotonic()
        last_emit = 0.0
        session_bytes = 0

        with part.open(mode) as handle:
            while True:
                _check_cancelled(is_cancelled)
                chunk = response.read(CHUNK_SIZE)
                if not chunk:
                    break
                handle.write(chunk)
                downloaded += len(chunk)
                session_bytes += len(chunk)

                now = time.monotonic()
                if on_progress and (now - last_emit >= 0.2 or downloaded == total):
                    last_emit = now
                    elapsed = max(now - started, 1e-6)
                    speed = session_bytes / elapsed
                    overall_done = base_downloaded + downloaded
                    percent = int(overall_done * 100 / overall_total) if overall_total else -1
                    eta = None
                    if speed > 0 and overall_total:
                        eta = max(overall_total - overall_done, 0) / speed
                    on_progress(
                        Progress(
                            label=display,
                            downloaded=overall_done,
                            total=overall_total,
                            percent=min(percent, 100) if percent >= 0 else -1,
                            speed_bps=speed,
                            eta_seconds=eta,
                            detail=display,
                        )
                    )

    part.replace(dest)
    return dest


def _is_within(root: Path, target: Path) -> bool:
    try:
        target.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def extract_archive(
    archive: Path,
    target_dir: Path,
    *,
    on_progress: ProgressCallback | None = None,
    label: str | None = None,
) -> Path:
    """Extract a zip/tar archive, refusing entries that escape ``target_dir``."""

    archive = Path(archive)
    target_dir = Path(target_dir)
    target_dir.mkdir(parents=True, exist_ok=True)
    display = label or archive.name

    if zipfile.is_zipfile(archive):
        with zipfile.ZipFile(archive) as bundle:
            members = bundle.namelist()
            for index, name in enumerate(members, start=1):
                destination = target_dir / name
                if not _is_within(target_dir, destination):
                    raise RuntimeError(f"Refusing to extract entry outside target: {name}")
                bundle.extract(name, target_dir)
                _emit_extract_progress(on_progress, display, index, len(members))
        return target_dir

    if tarfile.is_tarfile(archive):
        with tarfile.open(archive) as bundle:
            members = bundle.getmembers()
            for index, member in enumerate(members, start=1):
                destination = target_dir / member.name
                if not _is_within(target_dir, destination):
                    raise RuntimeError(f"Refusing to extract entry outside target: {member.name}")
                bundle.extract(member, target_dir)
                _emit_extract_progress(on_progress, display, index, len(members))
        return target_dir

    raise RuntimeError(f"Unsupported archive format: {archive.name}")


def _emit_extract_progress(
    on_progress: ProgressCallback | None, label: str, index: int, total: int
) -> None:
    if not on_progress or not total:
        return
    if index % 25 and index != total:
        return
    on_progress(
        Progress(
            label=label,
            downloaded=index,
            total=total,
            percent=int(index * 100 / total),
            detail=f"Extracting {index}/{total} files",
        )
    )


def flatten_single_root(directory: Path) -> Path:
    """Collapse ``dir/only-child/*`` into ``dir/*`` (archives love a wrapper folder)."""

    directory = Path(directory)
    entries = [item for item in directory.iterdir() if item.name != "__MACOSX"]
    if len(entries) != 1 or not entries[0].is_dir():
        return directory

    inner = entries[0]
    for item in list(inner.iterdir()):
        shutil.move(str(item), str(directory / item.name))
    inner.rmdir()
    return directory


def find_first(root: Path, names: Iterable[str]) -> Path | None:
    """Locate the first file matching any of ``names`` anywhere under ``root``."""

    for name in names:
        matches = sorted(Path(root).rglob(name))
        if matches:
            return matches[0]
    return None
