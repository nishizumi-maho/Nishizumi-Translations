"""Chooses a translation back-end and runs it over a master document."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Iterable, Sequence

from ..models import MasterDocument
from ..progress import ProgressEvent, stage_percent
from ..runtime.manager import manager
from .languages import Language, resolve_many
from .providers import (
    Cancelled,
    DeepLProvider,
    OfflineProvider,
    OpenAICompatibleProvider,
    Provider,
)

OFFLINE = "offline"
DEEPL = "deepl"
OPENAI = "openai"


@dataclass(frozen=True)
class EngineInfo:
    key: str
    name: str
    description: str
    ready: bool
    reason: str = ""
    needs_key: bool = False


def available_engines(cfg=None) -> list[EngineInfo]:
    """Every engine, with whether it is usable right now and why not."""

    from ..config import load_config

    cfg = cfg or load_config()
    translation = cfg.translation

    offline_ready = manager.has_translation_model()
    engines = [
        EngineInfo(
            key=OFFLINE,
            name="Offline translator",
            description="Runs on this machine. No account, nothing sent anywhere.",
            ready=offline_ready,
            reason="" if offline_ready else "Install the offline translator on the Components page.",
        ),
        EngineInfo(
            key=DEEPL,
            name="DeepL",
            description="High quality for everyday dialogue. Needs a DeepL API key.",
            ready=bool((translation.deepl_api_key or "").strip()),
            reason="" if (translation.deepl_api_key or "").strip() else "Add a DeepL API key in Settings.",
            needs_key=True,
        ),
        EngineInfo(
            key=OPENAI,
            name="OpenAI-compatible",
            description="Best with names and slang. Works with OpenAI, OpenRouter, LM Studio or Ollama.",
            ready=bool((translation.openai_base_url or "").strip()),
            reason="" if (translation.openai_base_url or "").strip() else "Set an endpoint in Settings.",
            needs_key=True,
        ),
    ]
    return engines


def is_translation_available(cfg=None) -> tuple[bool, str]:
    """Whether at least one engine can run, and why not when none can."""

    engines = available_engines(cfg)
    if any(engine.ready for engine in engines):
        return True, ""
    return False, "No translation engine is ready. " + engines[0].reason


def build_provider(engine: str, cfg=None) -> Provider:
    """Construct the provider named by ``engine``, or raise a helpful error."""

    from ..config import load_config

    cfg = cfg or load_config()
    settings = cfg.translation
    choice = (engine or settings.provider or OFFLINE).strip().lower()

    if choice == DEEPL:
        return DeepLProvider(api_key=settings.deepl_api_key or "")

    if choice == OPENAI:
        return OpenAICompatibleProvider(
            api_key=settings.openai_api_key or "",
            base_url=settings.openai_base_url or "https://api.openai.com/v1",
            model=settings.openai_model or "gpt-4o-mini",
        )

    model_dir = manager.translation_model_path()
    if not model_dir:
        raise RuntimeError(
            "The offline translator is not installed yet. Add it from the Components page, "
            "or run 'jp2subs components install translator'."
        )
    return OfflineProvider(model_dir=model_dir)


def translate_document(
    doc: MasterDocument,
    target_langs: Iterable[str] | Sequence[Language],
    *,
    engine: str = OFFLINE,
    provider: Provider | None = None,
    block_size: int = 16,
    cfg=None,
    on_progress: Callable[[ProgressEvent], None] | None = None,
    is_cancelled: Callable[[], bool] | None = None,
) -> MasterDocument:
    """Fill ``segment.translations[code]`` for each requested language."""

    languages = _as_languages(target_langs)
    if not languages:
        raise ValueError("Pick at least one target language.")
    if not doc.segments:
        return doc

    worker = provider or build_provider(engine, cfg)

    blocks_per_language = (len(doc.segments) + block_size - 1) // block_size
    total_blocks = max(1, blocks_per_language * len(languages))
    completed = 0

    for language in languages:
        doc.ensure_translation_key(language.code)
        for start in range(0, len(doc.segments), block_size):
            if is_cancelled and is_cancelled():
                raise Cancelled("Job cancelled")

            block = doc.segments[start : start + block_size]
            sources = [segment.ja_raw for segment in block]
            translated = worker.translate(sources, language, is_cancelled=is_cancelled)

            for segment, text in zip(block, translated):
                segment.translations[language.code] = text

            completed += 1
            if on_progress:
                done = min(start + len(block), len(doc.segments))
                on_progress(
                    ProgressEvent(
                        stage="Translate",
                        percent=stage_percent("Translate", completed / total_blocks),
                        message=f"Translating to {language.name}...",
                        detail=f"{done}/{len(doc.segments)} lines · {language.name}",
                    )
                )

    if isinstance(worker, OfflineProvider):
        worker.unload()

    if on_progress:
        on_progress(
            ProgressEvent(
                stage="Translate",
                percent=stage_percent("Translate", 1),
                message="Translation complete",
            )
        )
    return doc


def _as_languages(values: Iterable[str] | Sequence[Language]) -> list[Language]:
    items = list(values or [])
    if items and isinstance(items[0], Language):
        return list(items)  # type: ignore[arg-type]
    return resolve_many([str(item) for item in items])
