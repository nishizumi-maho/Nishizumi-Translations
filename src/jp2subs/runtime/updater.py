"""Check GitHub for newer releases and install them without leaving the app."""
from __future__ import annotations

import os
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from .. import __version__
from . import store
from .download import CancelCheck, ProgressCallback, download_file, fetch_json

REPO = "nishizumi-maho/Nishizumi-Translations"
RELEASES_API = f"https://api.github.com/repos/{REPO}/releases"
RELEASES_PAGE = f"https://github.com/{REPO}/releases"

_VERSION_RE = re.compile(r"^\s*v?(\d+)\.(\d+)\.(\d+)(?:[-.]?([0-9A-Za-z.\-]+))?\s*$")


@dataclass(frozen=True)
class ReleaseInfo:
    """A published release, reduced to what the update dialog needs."""

    version: str
    tag: str
    name: str
    notes: str
    html_url: str
    published_at: str = ""
    prerelease: bool = False
    asset_name: str = ""
    asset_url: str = ""
    asset_size: int = 0

    @property
    def has_installer(self) -> bool:
        return bool(self.asset_url)


def current_version() -> str:
    return __version__


def parse_version(text: str) -> tuple[int, int, int, str] | None:
    """Split ``v2.1.0`` / ``2.1.0-rc1`` into comparable parts."""

    match = _VERSION_RE.match(text or "")
    if not match:
        return None
    major, minor, patch, suffix = match.groups()
    return int(major), int(minor), int(patch), (suffix or "")


def is_newer(candidate: str, baseline: str) -> bool:
    """True when ``candidate`` is a strictly newer version than ``baseline``.

    A release with no pre-release suffix beats one that has it, so ``2.1.0``
    is newer than ``2.1.0-rc1``.
    """

    left = parse_version(candidate)
    right = parse_version(baseline)
    if left is None or right is None:
        return False
    if left[:3] != right[:3]:
        return left[:3] > right[:3]
    left_suffix, right_suffix = left[3], right[3]
    if left_suffix == right_suffix:
        return False
    if not left_suffix:
        return True
    if not right_suffix:
        return False
    return left_suffix > right_suffix


def _pick_asset(assets: list[dict]) -> tuple[str, str, int]:
    """Choose the best downloadable artifact for the running platform."""

    def score(name: str) -> int:
        lowered = name.lower()
        if sys.platform.startswith("win"):
            if lowered.endswith(".exe") and "setup" in lowered:
                return 100
            if lowered.endswith(".exe"):
                return 90
            if "win" in lowered and lowered.endswith(".zip"):
                return 60
        elif sys.platform == "darwin":
            if lowered.endswith(".dmg"):
                return 100
            if "macos" in lowered and lowered.endswith(".zip"):
                return 80
        else:
            if lowered.endswith(".appimage"):
                return 100
            if "linux" in lowered and lowered.endswith((".tar.gz", ".zip")):
                return 80
        return 0

    best: tuple[int, str, str, int] = (0, "", "", 0)
    for asset in assets:
        name = str(asset.get("name", ""))
        if name.lower().endswith((".sha256", ".txt", ".asc")):
            continue
        value = score(name)
        if value > best[0]:
            best = (value, name, str(asset.get("browser_download_url", "")), int(asset.get("size") or 0))
    return best[1], best[2], best[3]


def _to_release(payload: dict) -> ReleaseInfo:
    tag = str(payload.get("tag_name", ""))
    name, url, size = _pick_asset(list(payload.get("assets") or []))
    return ReleaseInfo(
        version=tag.lstrip("vV"),
        tag=tag,
        name=str(payload.get("name") or tag),
        notes=str(payload.get("body") or ""),
        html_url=str(payload.get("html_url") or RELEASES_PAGE),
        published_at=str(payload.get("published_at") or ""),
        prerelease=bool(payload.get("prerelease")),
        asset_name=name,
        asset_url=url,
        asset_size=size,
    )


def latest_release(*, include_prerelease: bool = False) -> ReleaseInfo | None:
    """Newest published release, ignoring drafts."""

    payloads = fetch_json(f"{RELEASES_API}?per_page=20")
    if isinstance(payloads, dict):  # pragma: no cover - defensive
        payloads = [payloads]

    best: ReleaseInfo | None = None
    for payload in payloads:
        if payload.get("draft"):
            continue
        if payload.get("prerelease") and not include_prerelease:
            continue
        release = _to_release(payload)
        if not parse_version(release.tag):
            continue
        if best is None or is_newer(release.version, best.version):
            best = release
    return best


def check_for_updates(*, include_prerelease: bool = False) -> ReleaseInfo | None:
    """The latest release when it is newer than what is running, else ``None``."""

    release = latest_release(include_prerelease=include_prerelease)
    if release and is_newer(release.version, current_version()):
        return release
    return None


def download_update(
    release: ReleaseInfo,
    *,
    on_progress: ProgressCallback | None = None,
    is_cancelled: CancelCheck | None = None,
) -> Path:
    """Fetch the release artifact into the local cache and return its path."""

    if not release.has_installer:
        raise RuntimeError("This release has no downloadable installer for your platform.")
    store.ensure_dirs()
    target = store.cache_dir() / "updates" / release.tag / release.asset_name
    if target.exists() and release.asset_size and target.stat().st_size == release.asset_size:
        return target
    return download_file(
        release.asset_url,
        target,
        label=release.asset_name,
        on_progress=on_progress,
        is_cancelled=is_cancelled,
        expected_size=release.asset_size,
    )


def is_frozen() -> bool:
    """True when running from a PyInstaller bundle rather than a source checkout."""

    return bool(getattr(sys, "frozen", False))


def launch_installer(path: Path) -> None:
    """Start the downloaded installer and leave it to take over.

    The caller is expected to quit straight after so the installer can replace
    files that are currently in use.
    """

    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Installer not found: {path}")

    if sys.platform.startswith("win"):
        if path.suffix.lower() == ".exe":
            os.startfile(str(path))  # type: ignore[attr-defined]  # noqa: S606
            return
        os.startfile(str(path.parent))  # type: ignore[attr-defined]  # noqa: S606
        return

    opener = "open" if sys.platform == "darwin" else "xdg-open"
    subprocess.Popen([opener, str(path)])  # noqa: S603
