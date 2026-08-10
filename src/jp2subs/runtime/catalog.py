"""Catalog of everything the app can install for the user.

This module is pure data plus a little platform logic. The download and install
mechanics live in :mod:`jp2subs.runtime.manager`.
"""
from __future__ import annotations

import platform
import sys
from dataclasses import dataclass, field
from enum import Enum


class ComponentKind(str, Enum):
    MODEL = "model"
    TOOL = "tool"
    ACCELERATION = "acceleration"


@dataclass(frozen=True)
class Component:
    """One installable item shown in the app's Components page."""

    key: str
    name: str
    kind: ComponentKind
    summary: str
    #: Approximate download size in bytes, used before the real size is known.
    approx_size: int = 0
    #: Hugging Face repository for CTranslate2 Whisper models.
    repo_id: str = ""
    #: Direct download used by tools that are not fetched from Hugging Face.
    url: str = ""
    #: PyPI distributions bundled into an acceleration pack.
    wheels: tuple[tuple[str, str], ...] = ()
    #: Whisper model alias understood by faster-whisper (``large-v3`` etc).
    model_alias: str = ""
    quality: str = ""
    speed: str = ""
    recommended: bool = False
    required: bool = False
    notes: str = ""
    tags: tuple[str, ...] = field(default_factory=tuple)

    @property
    def is_model(self) -> bool:
        return self.kind is ComponentKind.MODEL


GB = 1024 ** 3
MB = 1024 ** 2

# --- Whisper models -------------------------------------------------------
# All entries are CTranslate2 conversions, which is the format faster-whisper
# loads directly from a folder.

_MODELS: tuple[Component, ...] = (
    Component(
        key="model:tiny",
        name="Whisper Tiny",
        kind=ComponentKind.MODEL,
        summary="Fastest option. Good for a quick draft or testing the pipeline.",
        approx_size=75 * MB,
        repo_id="Systran/faster-whisper-tiny",  # measured 74.6 MB
        model_alias="tiny",
        quality="Basic",
        speed="Fastest",
        tags=("cpu-friendly",),
    ),
    Component(
        key="model:base",
        name="Whisper Base",
        kind=ComponentKind.MODEL,
        summary="Small step up from Tiny. Still comfortable on a laptop CPU.",
        approx_size=141 * MB,
        repo_id="Systran/faster-whisper-base",
        model_alias="base",
        quality="Basic",
        speed="Very fast",
        tags=("cpu-friendly",),
    ),
    Component(
        key="model:small",
        name="Whisper Small",
        kind=ComponentKind.MODEL,
        summary="Reasonable Japanese accuracy without a GPU. A sensible CPU default.",
        approx_size=464 * MB,
        repo_id="Systran/faster-whisper-small",
        model_alias="small",
        quality="Good",
        speed="Fast",
        tags=("cpu-friendly",),
    ),
    Component(
        key="model:medium",
        name="Whisper Medium",
        kind=ComponentKind.MODEL,
        summary="Noticeably better on fast speech and background noise.",
        approx_size=1450 * MB,
        repo_id="Systran/faster-whisper-medium",
        model_alias="medium",
        quality="Very good",
        speed="Moderate",
    ),
    Component(
        key="model:large-v3-turbo",
        name="Whisper Large v3 Turbo",
        kind=ComponentKind.MODEL,
        summary="Near large-v3 accuracy at a fraction of the runtime. Best all-round pick.",
        approx_size=1550 * MB,
        repo_id="mobiuslabsgmbh/faster-whisper-large-v3-turbo",
        model_alias="large-v3-turbo",
        quality="Excellent",
        speed="Fast",
        recommended=True,
        tags=("recommended",),
    ),
    Component(
        key="model:distil-large-v3",
        name="Distil Whisper Large v3",
        kind=ComponentKind.MODEL,
        summary="Distilled large model. Quick, but tuned for English more than Japanese.",
        approx_size=1450 * MB,
        repo_id="Systran/faster-distil-whisper-large-v3",
        model_alias="distil-large-v3",
        quality="Good",
        speed="Fast",
        notes="Optimised for English; Japanese accuracy trails the standard large models.",
    ),
    Component(
        key="model:large-v2",
        name="Whisper Large v2",
        kind=ComponentKind.MODEL,
        summary="Previous flagship. Some sources still prefer its punctuation style.",
        approx_size=2950 * MB,
        repo_id="Systran/faster-whisper-large-v2",
        model_alias="large-v2",
        quality="Excellent",
        speed="Slow",
    ),
    Component(
        key="model:large-v3",
        name="Whisper Large v3",
        kind=ComponentKind.MODEL,
        summary="Highest accuracy for Japanese. Wants a GPU or a lot of patience.",
        approx_size=2950 * MB,
        repo_id="Systran/faster-whisper-large-v3",
        model_alias="large-v3",
        quality="Best",
        speed="Slow",
        tags=("best-quality",),
    ),
)

# --- ffmpeg ---------------------------------------------------------------

_FFMPEG_WINDOWS = Component(
    key="tool:ffmpeg",
    name="FFmpeg",
    kind=ComponentKind.TOOL,
    summary="Extracts audio, muxes and burns subtitles. The app cannot run without it.",
    approx_size=163 * MB,
    url="https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-win64-gpl.zip",
    required=True,
    recommended=True,
)

_FFMPEG_LINUX = Component(
    key="tool:ffmpeg",
    name="FFmpeg",
    kind=ComponentKind.TOOL,
    summary="Extracts audio, muxes and burns subtitles. The app cannot run without it.",
    approx_size=80 * MB,
    url="https://johnvansickle.com/ffmpeg/releases/ffmpeg-release-amd64-static.tar.xz",
    required=True,
    recommended=True,
)

_FFMPEG_MACOS = Component(
    key="tool:ffmpeg",
    name="FFmpeg",
    kind=ComponentKind.TOOL,
    summary="Extracts audio, muxes and burns subtitles. The app cannot run without it.",
    approx_size=40 * MB,
    url="https://evermeet.cx/ffmpeg/getrelease/ffmpeg/zip",
    required=True,
    recommended=True,
    notes="ffprobe is downloaded alongside ffmpeg.",
)

# --- GPU acceleration -----------------------------------------------------

_CUDA_PACK = Component(
    key="accel:cuda",
    name="NVIDIA GPU acceleration",
    kind=ComponentKind.ACCELERATION,
    summary="cuBLAS and cuDNN libraries that let transcription run on an NVIDIA GPU.",
    approx_size=1230 * MB,
    wheels=(
        ("nvidia-cublas-cu12", "12"),
        ("nvidia-cudnn-cu12", "9"),
    ),
    notes="Only useful with an NVIDIA card and a recent driver. CPU transcription works without it.",
)


def is_windows() -> bool:
    return sys.platform.startswith("win")


def is_x64() -> bool:
    machine = platform.machine().lower()
    return machine in {"amd64", "x86_64", "x64"}


def ffmpeg_component() -> Component:
    if is_windows():
        return _FFMPEG_WINDOWS
    if sys.platform == "darwin":
        return _FFMPEG_MACOS
    return _FFMPEG_LINUX


def models() -> tuple[Component, ...]:
    """Whisper models, ordered the way the UI should list them."""

    return _MODELS


def cuda_component() -> Component | None:
    """The GPU pack, when the current platform can actually use it."""

    if is_windows() and is_x64():
        return _CUDA_PACK
    return None


def all_components() -> tuple[Component, ...]:
    items: list[Component] = [ffmpeg_component()]
    items.extend(_MODELS)
    cuda = cuda_component()
    if cuda:
        items.append(cuda)
    return tuple(items)


def component(key: str) -> Component | None:
    for item in all_components():
        if item.key == key:
            return item
    return None


def model_for_alias(alias: str) -> Component | None:
    """Find the catalog entry for a faster-whisper model name such as ``large-v3``."""

    normalized = (alias or "").strip().lower()
    if not normalized:
        return None
    for item in _MODELS:
        if item.model_alias == normalized or item.key == normalized:
            return item
    return None


def recommended_model_key() -> str:
    for item in _MODELS:
        if item.recommended:
            return item.key
    return _MODELS[0].key
