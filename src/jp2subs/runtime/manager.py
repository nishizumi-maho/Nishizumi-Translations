"""Install, inspect and remove the components jp2subs downloads for itself."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

from . import catalog, store
from .catalog import Component, ComponentKind
from .download import (
    CancelCheck,
    DownloadCancelled,
    Progress,
    ProgressCallback,
    download_file,
    extract_archive,
    fetch_json,
    find_first,
    flatten_single_root,
    remote_size,
)

HF_API = "https://huggingface.co/api/models"
HF_RESOLVE = "https://huggingface.co/{repo}/resolve/main/{path}"
PYPI_API = "https://pypi.org/pypi/{dist}/json"

#: Files that live in Hugging Face repos but are useless to faster-whisper.
_SKIP_SUFFIXES = {
    ".md",
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".svg",
    ".pt",
    ".pth",
    ".safetensors",
    ".onnx",
    ".msgpack",
    ".h5",
    ".tflite",
    ".ot",
}
_SKIP_NAMES = {".gitattributes", ".gitignore"}

_MODEL_MARKER = "config.json"
_MODEL_WEIGHTS = "model.bin"


@dataclass
class ComponentStatus:
    """What the UI needs to render one row of the Components page."""

    component: Component
    installed: bool
    path: Path | None = None
    size: int = 0
    version: str = ""
    installed_at: str = ""

    @property
    def key(self) -> str:
        return self.component.key


class ComponentManager:
    """Owns the download directory and the record of what lives in it."""

    def __init__(self) -> None:
        self._manifest_cache: dict[str, dict] | None = None

    # -- manifest ---------------------------------------------------------

    def _manifest(self) -> dict[str, dict]:
        if self._manifest_cache is None:
            path = store.manifest_path()
            if path.exists():
                try:
                    self._manifest_cache = json.loads(path.read_text(encoding="utf-8"))
                except (json.JSONDecodeError, OSError):
                    self._manifest_cache = {}
            else:
                self._manifest_cache = {}
        return self._manifest_cache

    def _write_manifest(self) -> None:
        store.ensure_dirs()
        store.manifest_path().write_text(
            json.dumps(self._manifest(), indent=2, sort_keys=True), encoding="utf-8"
        )

    def _record(self, key: str, path: Path, *, version: str = "", component: Component | None = None) -> None:
        entry = {
            "path": str(path),
            "version": version,
            "size": store.dir_size(path),
            "installed_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        }
        if component is not None and component.custom:
            # Custom models are not in the catalog, so the manifest has to carry
            # enough to rebuild the component after a restart.
            entry.update(
                {
                    "custom": True,
                    "repo_id": component.repo_id,
                    "name": component.name,
                    "approx_size": component.approx_size,
                }
            )
        self._manifest()[key] = entry
        self._write_manifest()

    # -- custom (searched) models ----------------------------------------

    def custom_components(self) -> list[Component]:
        """Components rebuilt from manifest entries added via repository search."""

        items: list[Component] = []
        for key, record in self._manifest().items():
            if not record.get("custom"):
                continue
            repo_id = str(record.get("repo_id") or "")
            if not repo_id:
                continue
            items.append(
                catalog.custom_model(
                    repo_id,
                    approx_size=int(record.get("approx_size") or 0),
                    name=str(record.get("name") or ""),
                )
            )
            if items[-1].key != key:  # pragma: no cover - manifest written by an older build
                items[-1] = catalog.custom_model(repo_id)
        return items

    def _resolve_component(self, key: str) -> Component | None:
        """Look a key up in the catalog, then among installed custom models."""

        found = catalog.component(key)
        if found:
            return found
        for item in self.custom_components():
            if item.key == key:
                return item
        return None

    def _forget(self, key: str) -> None:
        self._manifest().pop(key, None)
        self._write_manifest()

    def refresh(self) -> None:
        """Drop cached manifest state so the next read hits disk."""

        self._manifest_cache = None

    def rebase(self) -> None:
        """Re-read the manifest and repoint it at the current data directory.

        Called after the user moves their components to another drive: the
        manifest travels with the files, so only the absolute paths it records
        are stale.
        """

        self.refresh()
        manifest = self._manifest()
        changed = False
        for key, record in manifest.items():
            item = self._resolve_component(key)
            if not item:
                continue
            path = str(self.install_path(item))
            if record.get("path") != path:
                record["path"] = path
                changed = True
        if changed:
            self._write_manifest()

    # -- paths ------------------------------------------------------------

    def install_path(self, item: Component) -> Path:
        if item.kind is ComponentKind.MODEL:
            return store.models_dir() / (item.model_alias or catalog.custom_slug(item.repo_id))
        if item.kind is ComponentKind.TRANSLATION:
            return store.models_dir() / "translation" / item.key.split(":", 1)[-1]
        if item.key == "tool:ffmpeg":
            return store.tools_dir() / "ffmpeg"
        if item.kind is ComponentKind.ACCELERATION:
            return store.tools_dir() / "cuda"
        return store.tools_dir() / item.key.split(":", 1)[-1]

    # -- status -----------------------------------------------------------

    def is_installed(self, key: str) -> bool:
        item = self._resolve_component(key)
        if not item:
            return False
        path = self.install_path(item)
        if item.kind in (ComponentKind.MODEL, ComponentKind.TRANSLATION):
            return (path / _MODEL_MARKER).exists() and (path / _MODEL_WEIGHTS).exists()
        if item.key == "tool:ffmpeg":
            return self._managed_ffmpeg() is not None
        if item.kind is ComponentKind.ACCELERATION:
            return path.exists() and any(path.rglob("*.dll"))
        return path.exists()

    def status(self, key: str) -> ComponentStatus | None:
        item = self._resolve_component(key)
        if not item:
            return None
        installed = self.is_installed(key)
        path = self.install_path(item)
        record = self._manifest().get(key, {})
        return ComponentStatus(
            component=item,
            installed=installed,
            path=path if installed else None,
            size=store.dir_size(path) if installed else 0,
            version=str(record.get("version", "")),
            installed_at=str(record.get("installed_at", "")),
        )

    def statuses(self, items: Iterable[Component] | None = None) -> list[ComponentStatus]:
        source = list(items) if items is not None else list(catalog.all_components())
        result: list[ComponentStatus] = []
        for item in source:
            status = self.status(item.key)
            if status:
                result.append(status)
        return result

    def installed_models(self) -> list[Component]:
        """Every usable speech model: catalog entries first, then searched ones."""

        installed = [item for item in catalog.models() if self.is_installed(item.key)]
        installed.extend(item for item in self.custom_components() if self.is_installed(item.key))
        return installed

    def missing_required(self) -> list[Component]:
        """Components without which the app cannot do its job."""

        missing = [item for item in catalog.all_components() if item.required and not self.is_installed(item.key)]
        if item_ffmpeg_on_path() and any(item.key == "tool:ffmpeg" for item in missing):
            missing = [item for item in missing if item.key != "tool:ffmpeg"]
        if not self.installed_models():
            recommended = catalog.component(catalog.recommended_model_key())
            if recommended:
                missing.append(recommended)
        return missing

    def is_ready(self) -> bool:
        return not self.missing_required()

    def total_size(self) -> int:
        return store.dir_size(store.data_dir())

    # -- model resolution -------------------------------------------------

    def model_path(self, alias_or_key: str) -> Path | None:
        item = catalog.model_for_alias(alias_or_key) or catalog.component(alias_or_key)
        if item is None:
            item = self._custom_model_for(alias_or_key)
        if not item or not item.is_model:
            return None
        path = self.install_path(item)
        return path if self.is_installed(item.key) else None

    def _custom_model_for(self, name: str) -> Component | None:
        """Match a searched model by its slug, its repository id, or its key."""

        needle = (name or "").strip()
        if not needle:
            return None
        lowered = needle.lower()
        for item in self.custom_components():
            if lowered in {item.model_alias.lower(), item.repo_id.lower(), item.key.lower()}:
                return item
        return None

    def resolve_model(self, name: str) -> str:
        """Turn a model name into something faster-whisper can load.

        A managed model becomes an absolute folder path so no network access is
        needed at transcription time. Anything else (a custom local path, or an
        alias we do not manage) is handed back untouched.
        """

        raw = (name or "").strip()
        if not raw:
            return raw
        candidate = Path(raw).expanduser()
        if candidate.exists() and candidate.is_dir():
            return str(candidate)
        managed = self.model_path(raw)
        return str(managed) if managed else raw

    def default_model(self) -> str:
        """Best installed model alias, or the recommended one if nothing is installed."""

        installed = self.installed_models()
        if installed:
            for item in installed:
                if item.recommended:
                    return item.model_alias
            return installed[0].model_alias
        item = catalog.component(catalog.recommended_model_key())
        return item.model_alias if item else "large-v3-turbo"

    # -- translation ------------------------------------------------------

    def translation_model_path(self, key: str = "") -> Path | None:
        """Folder of the installed offline translation model, if there is one."""

        candidates = (
            [catalog.component(key)] if key else list(catalog.translation_models())
        )
        for item in candidates:
            if item and self.is_installed(item.key):
                return self.install_path(item)
        return None

    def has_translation_model(self) -> bool:
        return self.translation_model_path() is not None

    # -- ffmpeg -----------------------------------------------------------

    def _managed_ffmpeg(self) -> Path | None:
        root = store.tools_dir() / "ffmpeg"
        if not root.exists():
            return None
        names = ("ffmpeg.exe",) if sys.platform.startswith("win") else ("ffmpeg",)
        found = find_first(root, names)
        return found if found and found.is_file() else None

    def ffmpeg_binary(self) -> str | None:
        found = self._managed_ffmpeg()
        return str(found) if found else None

    def ffprobe_binary(self) -> str | None:
        ffmpeg = self._managed_ffmpeg()
        if not ffmpeg:
            return None
        name = "ffprobe.exe" if sys.platform.startswith("win") else "ffprobe"
        sibling = ffmpeg.with_name(name)
        if sibling.exists():
            return str(sibling)
        found = find_first(store.tools_dir() / "ffmpeg", (name,))
        return str(found) if found else None

    # -- CUDA -------------------------------------------------------------

    def cuda_bin_dir(self) -> Path | None:
        root = store.tools_dir() / "cuda"
        if root.exists() and any(root.rglob("*.dll")):
            return root
        return None

    def activate_cuda(self) -> bool:
        """Make managed CUDA libraries loadable by CTranslate2 in this process."""

        root = self.cuda_bin_dir()
        if not root:
            return False
        dll_dirs = {path.parent for path in root.rglob("*.dll")}
        for directory in sorted(dll_dirs):
            text = str(directory)
            if sys.platform.startswith("win") and hasattr(os, "add_dll_directory"):
                try:
                    os.add_dll_directory(text)
                except (OSError, FileNotFoundError):  # pragma: no cover - defensive
                    continue
            if text not in os.environ.get("PATH", "").split(os.pathsep):
                os.environ["PATH"] = text + os.pathsep + os.environ.get("PATH", "")
        return True

    # -- install ----------------------------------------------------------

    def install_custom_model(
        self,
        repo_id: str,
        *,
        approx_size: int = 0,
        name: str = "",
        on_progress: ProgressCallback | None = None,
        is_cancelled: CancelCheck | None = None,
    ) -> Path:
        """Install any CTranslate2 Whisper repository found through search."""

        component = catalog.custom_model(repo_id, approx_size=approx_size, name=name)
        return self.install(
            component.key, component=component, on_progress=on_progress, is_cancelled=is_cancelled
        )

    def install(
        self,
        key: str,
        *,
        component: Component | None = None,
        on_progress: ProgressCallback | None = None,
        is_cancelled: CancelCheck | None = None,
    ) -> Path:
        item = component or self._resolve_component(key)
        if not item:
            raise ValueError(f"Unknown component: {key}")

        store.ensure_dirs()
        final = self.install_path(item)
        staging = final.with_name(final.name + ".incomplete")
        store.remove_path(staging)
        staging.mkdir(parents=True, exist_ok=True)

        try:
            if item.kind in (ComponentKind.MODEL, ComponentKind.TRANSLATION):
                version = self._install_model(item, staging, on_progress, is_cancelled)
            elif item.key == "tool:ffmpeg":
                version = self._install_ffmpeg(item, staging, on_progress, is_cancelled)
            elif item.kind is ComponentKind.ACCELERATION:
                version = self._install_wheels(item, staging, on_progress, is_cancelled)
            else:  # pragma: no cover - no other kinds today
                raise ValueError(f"No installer for component kind {item.kind}")
        except DownloadCancelled:
            store.remove_path(staging)
            raise
        except Exception:
            store.remove_path(staging)
            raise

        store.remove_path(final)
        final.parent.mkdir(parents=True, exist_ok=True)
        staging.replace(final)
        self._record(item.key, final, version=version, component=item)
        _emit(on_progress, item.name, 100, f"{item.name} installed")
        return final

    def uninstall(self, key: str) -> None:
        item = self._resolve_component(key)
        if not item:
            raise ValueError(f"Unknown component: {key}")
        path = self.install_path(item)
        store.remove_path(path)
        store.remove_path(path.with_name(path.name + ".incomplete"))
        self._forget(item.key)

    # -- installers -------------------------------------------------------

    def _install_model(
        self,
        item: Component,
        staging: Path,
        on_progress: ProgressCallback | None,
        is_cancelled: CancelCheck | None,
    ) -> str:
        _emit(on_progress, item.name, 0, f"Looking up {item.repo_id}")
        files = self._model_files(item.repo_id)
        if not files:
            raise RuntimeError(f"No downloadable files found in {item.repo_id}")

        sized: list[tuple[str, str, int]] = []
        total = 0
        for relative in files:
            url = HF_RESOLVE.format(repo=item.repo_id, path=relative)
            size = remote_size(url)
            sized.append((relative, url, size))
            total += size
        if not total:
            total = item.approx_size

        done = 0
        for relative, url, size in sized:
            destination = staging / relative
            download_file(
                url,
                destination,
                label=f"{item.name} · {relative}",
                on_progress=on_progress,
                is_cancelled=is_cancelled,
                expected_size=size,
                base_downloaded=done,
                base_total=total,
            )
            done += size or destination.stat().st_size

        if not (staging / _MODEL_MARKER).exists() or not (staging / _MODEL_WEIGHTS).exists():
            raise RuntimeError(
                f"{item.repo_id} did not provide {_MODEL_MARKER} and {_MODEL_WEIGHTS}; "
                "the repository layout may have changed."
            )
        return item.repo_id

    def _model_files(self, repo_id: str) -> list[str]:
        data = fetch_json(f"{HF_API}/{repo_id}")
        siblings = data.get("siblings") or []
        names = [str(entry.get("rfilename", "")) for entry in siblings]
        return [name for name in names if name and _keep_model_file(name)]

    def _install_ffmpeg(
        self,
        item: Component,
        staging: Path,
        on_progress: ProgressCallback | None,
        is_cancelled: CancelCheck | None,
    ) -> str:
        urls = [item.url]
        if sys.platform == "darwin":
            urls.append("https://evermeet.cx/ffmpeg/getrelease/ffprobe/zip")

        downloads = staging / "_download"
        downloads.mkdir(parents=True, exist_ok=True)
        for index, url in enumerate(urls):
            archive = downloads / f"ffmpeg-{index}{_archive_suffix(url)}"
            _emit(on_progress, item.name, 0, f"Downloading {item.name}")
            download_file(
                url,
                archive,
                label=item.name,
                on_progress=on_progress,
                is_cancelled=is_cancelled,
                expected_size=item.approx_size,
            )
            _emit(on_progress, item.name, -1, "Extracting FFmpeg")
            extract_archive(archive, staging, on_progress=on_progress, label=item.name)
            archive.unlink(missing_ok=True)

        shutil.rmtree(downloads, ignore_errors=True)
        flatten_single_root(staging)

        binary_names = ("ffmpeg.exe",) if sys.platform.startswith("win") else ("ffmpeg",)
        binary = find_first(staging, binary_names)
        if not binary:
            raise RuntimeError("The downloaded FFmpeg archive did not contain an ffmpeg binary.")
        if not sys.platform.startswith("win"):
            for name in ("ffmpeg", "ffprobe"):
                found = find_first(staging, (name,))
                if found:
                    found.chmod(found.stat().st_mode | 0o755)

        _emit(on_progress, item.name, -1, "Trimming unused FFmpeg files")
        _prune_ffmpeg(staging)
        return _ffmpeg_version(binary)

    def _install_wheels(
        self,
        item: Component,
        staging: Path,
        on_progress: ProgressCallback | None,
        is_cancelled: CancelCheck | None,
    ) -> str:
        resolved: list[tuple[str, str, str, int]] = []
        for dist, major in item.wheels:
            _emit(on_progress, item.name, 0, f"Resolving {dist}")
            version, url, size = _latest_wheel(dist, major)
            resolved.append((dist, version, url, size))

        total = sum(entry[3] for entry in resolved) or item.approx_size
        done = 0
        extracted = staging / "_wheels"
        extracted.mkdir(parents=True, exist_ok=True)

        for dist, version, url, size in resolved:
            wheel = extracted / f"{dist}-{version}.zip"
            download_file(
                url,
                wheel,
                label=f"{item.name} · {dist} {version}",
                on_progress=on_progress,
                is_cancelled=is_cancelled,
                expected_size=size,
                base_downloaded=done,
                base_total=total,
            )
            done += size or wheel.stat().st_size
            unpacked = extracted / dist
            extract_archive(wheel, unpacked, on_progress=on_progress, label=dist)
            wheel.unlink(missing_ok=True)

        # Keep only the shared libraries; the Python shims in the wheels are dead weight.
        moved = 0
        patterns = ("*.dll",) if sys.platform.startswith("win") else ("*.so", "*.so.*")
        for pattern in patterns:
            for library in extracted.rglob(pattern):
                target = staging / library.name
                if target.exists():
                    continue
                shutil.move(str(library), str(target))
                moved += 1
        shutil.rmtree(extracted, ignore_errors=True)

        if not moved:
            raise RuntimeError("The GPU acceleration download did not contain any runtime libraries.")
        return ", ".join(f"{dist} {version}" for dist, version, _url, _size in resolved)


# -- helpers ---------------------------------------------------------------


def _keep_model_file(name: str) -> bool:
    lowered = name.lower()
    if Path(lowered).name in _SKIP_NAMES:
        return False
    if any(lowered.endswith(suffix) for suffix in _SKIP_SUFFIXES):
        return False
    return True


def _archive_suffix(url: str) -> str:
    lowered = url.lower()
    for suffix in (".tar.xz", ".tar.gz", ".tar.bz2", ".zip", ".7z"):
        if lowered.endswith(suffix):
            return suffix
    return ".zip"


#: The static builds ship a media player and manuals we never invoke. On the
#: Windows GPL build that is well over 100 MB of dead weight.
_FFMPEG_KEEP_STEMS = {"ffmpeg", "ffprobe"}


def _prune_ffmpeg(root: Path) -> None:
    """Drop everything except the ffmpeg/ffprobe binaries and their libraries."""

    for item in list(root.rglob("*")):
        if not item.is_file():
            continue
        stem = item.stem.lower()
        suffix = item.suffix.lower()
        # Match the executables themselves, not documentation like doc/ffmpeg.html.
        if stem in _FFMPEG_KEEP_STEMS and suffix in {"", ".exe"}:
            continue
        if suffix in {".dll", ".so", ".dylib"} or ".so." in item.name:
            continue
        item.unlink(missing_ok=True)

    for directory in sorted(root.rglob("*"), key=lambda p: len(p.parts), reverse=True):
        if directory.is_dir() and not any(directory.iterdir()):
            directory.rmdir()


def _ffmpeg_version(binary: Path) -> str:
    """Ask the binary what it is, rather than guessing from a folder name."""

    try:
        result = subprocess.run(  # noqa: S603
            [str(binary), "-version"], capture_output=True, text=True, timeout=20
        )
    except (OSError, subprocess.SubprocessError):  # pragma: no cover - defensive
        return ""
    first_line = (result.stdout or "").splitlines()
    if not first_line:
        return ""
    parts = first_line[0].split()
    return parts[2] if len(parts) > 2 else first_line[0]


def _latest_wheel(dist: str, major: str) -> tuple[str, str, int]:
    """Newest ``dist`` release whose version starts with ``major`` and ships a wheel here."""

    data = fetch_json(PYPI_API.format(dist=dist))
    releases: dict[str, list[dict]] = data.get("releases") or {}
    tag = "win_amd64" if sys.platform.startswith("win") else "manylinux"

    def sort_key(version: str) -> tuple:
        parts = []
        for chunk in version.replace("-", ".").split("."):
            parts.append((0, int(chunk)) if chunk.isdigit() else (1, 0))
        return tuple(parts)

    candidates = [version for version in releases if version.split(".", 1)[0] == major]
    for version in sorted(candidates, key=sort_key, reverse=True):
        for entry in releases[version]:
            filename = str(entry.get("filename", ""))
            if filename.endswith(".whl") and tag in filename and not entry.get("yanked"):
                return version, str(entry["url"]), int(entry.get("size") or 0)

    raise RuntimeError(f"No {major}.x wheel of {dist} is available for this platform.")


def item_ffmpeg_on_path() -> bool:
    return shutil.which("ffmpeg") is not None


def _emit(on_progress: ProgressCallback | None, label: str, percent: int, detail: str) -> None:
    if on_progress:
        on_progress(Progress(label=label, percent=percent, detail=detail))


#: Shared instance; the GUI and CLI both use this rather than constructing their own.
manager = ComponentManager()
