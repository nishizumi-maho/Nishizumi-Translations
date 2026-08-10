"""Subtitle translation: offline NLLB-200, DeepL, or any OpenAI-compatible endpoint."""

from .engine import (
    DEEPL,
    OFFLINE,
    OPENAI,
    EngineInfo,
    available_engines,
    build_provider,
    is_translation_available,
    translate_document,
)
from .languages import LANGUAGES, SOURCE, Language, deepl_supported, get, resolve_many
from .providers import (
    Cancelled,
    DeepLProvider,
    OfflineProvider,
    OpenAICompatibleProvider,
    Provider,
    parse_numbered,
)

__all__ = [
    "Cancelled",
    "DEEPL",
    "DeepLProvider",
    "EngineInfo",
    "LANGUAGES",
    "Language",
    "OFFLINE",
    "OPENAI",
    "OfflineProvider",
    "OpenAICompatibleProvider",
    "Provider",
    "SOURCE",
    "available_engines",
    "build_provider",
    "deepl_supported",
    "get",
    "is_translation_available",
    "parse_numbered",
    "resolve_many",
    "translate_document",
]
