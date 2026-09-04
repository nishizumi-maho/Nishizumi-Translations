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
    TRANSLATION = "translation"
    TOOL = "tool"
    ACCELERATION = "acceleration"


class ModelFamily(str, Enum):
    """How speech models are grouped on the Components page."""

    GENERAL = "General purpose"
    JAPANESE = "Tuned for Japanese"
    CUSTOM = "Downloaded from Hugging Face"


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
    family: ModelFamily = ModelFamily.GENERAL
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

    #: Set for models installed by repository search rather than shipped in the catalog.
    custom: bool = False

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
    # --- Japanese fine-tunes -------------------------------------------
    Component(
        key="model:kotoba-v2",
        name="Kotoba Whisper v2.0",
        kind=ComponentKind.MODEL,
        summary="Distilled specifically for Japanese. Faster than Large v3 and often more accurate on it.",
        approx_size=1450 * MB,
        repo_id="kotoba-tech/kotoba-whisper-v2.0-faster",
        model_alias="kotoba-v2",
        quality="Excellent (Japanese)",
        speed="Fast",
        family=ModelFamily.JAPANESE,
        tags=("japanese",),
        notes="Japanese only. Trained on the ReazonSpeech corpus by Kotoba Technologies.",
    ),
    Component(
        key="model:kotoba-bilingual",
        name="Kotoba Whisper Bilingual v1.0",
        kind=ComponentKind.MODEL,
        summary="Japanese and English in one model, including direct Japanese-to-English speech translation.",
        approx_size=1450 * MB,
        repo_id="kotoba-tech/kotoba-whisper-bilingual-v1.0-faster",
        model_alias="kotoba-bilingual",
        quality="Very good",
        speed="Fast",
        family=ModelFamily.JAPANESE,
        tags=("japanese", "bilingual"),
    ),
    Component(
        key="model:large-v2-ja",
        name="Whisper Large v2 (Japanese tuned)",
        kind=ComponentKind.MODEL,
        summary="Large v2 fine-tuned a further 5k steps on Japanese. Heavy, but strong on hard audio.",
        approx_size=2950 * MB,
        repo_id="zh-plus/faster-whisper-large-v2-japanese-5k-steps",
        model_alias="large-v2-ja",
        quality="Excellent (Japanese)",
        speed="Slow",
        family=ModelFamily.JAPANESE,
        tags=("japanese",),
    ),
)

# --- Translation ----------------------------------------------------------
# CTranslate2 and tokenizers already ship with faster-whisper, so offline
# translation needs a model download and no extra Python dependency.

_TRANSLATION_MODELS: tuple[Component, ...] = (
    Component(
        key="translate:nllb-200-600m",
        name="NLLB-200 offline translator",
        kind=ComponentKind.TRANSLATION,
        summary="Translates subtitles into roughly 200 languages on your own machine. No account, no API key.",
        approx_size=1200 * MB,
        repo_id="JustFrederik/nllb-200-distilled-600M-ct2-float16",
        quality="Good",
        speed="Fast",
        recommended=True,
        notes="Meta's distilled 600M model. Solid on ordinary dialogue; proper nouns and slang are where online engines pull ahead.",
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


def models_by_family() -> dict[ModelFamily, tuple[Component, ...]]:
    """Speech models grouped for display, preserving catalog order."""

    grouped: dict[ModelFamily, list[Component]] = {}
    for item in _MODELS:
        grouped.setdefault(item.family, []).append(item)
    return {family: tuple(items) for family, items in grouped.items()}


def translation_models() -> tuple[Component, ...]:
    return _TRANSLATION_MODELS


def default_translation_model() -> Component:
    return _TRANSLATION_MODELS[0]


def custom_model(repo_id: str, *, approx_size: int = 0, name: str = "") -> Component:
    """Build a catalog entry for a repository the user found through search."""

    slug = custom_slug(repo_id)
    return Component(
        key=f"model:hf:{repo_id}",
        name=name or repo_id.split("/")[-1],
        kind=ComponentKind.MODEL,
        summary=f"Downloaded from Hugging Face: {repo_id}",
        approx_size=approx_size,
        repo_id=repo_id,
        model_alias=slug,
        family=ModelFamily.CUSTOM,
        custom=True,
    )


def custom_slug(repo_id: str) -> str:
    """Folder-safe identifier for a Hugging Face repository.

    The owner separator becomes a double underscore so ``owner/name`` cannot
    collide with a repository actually called ``owner_name``.
    """

    marked = repo_id.strip().replace("/", "__")
    cleaned = "".join(
        char if char.isalnum() or char in {"-", "_", "."} else "_" for char in marked
    )
    return cleaned.strip("._") or "custom-model"


def cuda_component() -> Component | None:
    """The GPU pack, when the current platform can actually use it."""

    if is_windows() and is_x64():
        return _CUDA_PACK
    return None


def all_components() -> tuple[Component, ...]:
    items: list[Component] = [ffmpeg_component()]
    items.extend(_MODELS)
    items.extend(_TRANSLATION_MODELS)
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
