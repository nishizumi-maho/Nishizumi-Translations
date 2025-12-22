"""Translation orchestration for jp2subs."""
from __future__ import annotations

import os
import shlex
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Dict, Iterable, List, Sequence

from rich.console import Console

from . import config as config_mod
from .models import MasterDocument
from .paths import strip_quotes
from .progress import ProgressEvent, stage_percent


def _normalize_path(raw: str | None) -> Path | None:
    if not raw:
        return None
    cleaned = strip_quotes(str(raw)).strip()
    if not cleaned:
        return None
    return Path(cleaned).expanduser()


def _load_config() -> config_mod.AppConfig | None:
    try:
        return config_mod.load_config()
    except Exception:  # pragma: no cover - config loading failures are not critical here
        return None


def is_translation_available(cfg: config_mod.AppConfig | None = None) -> tuple[bool, str]:
    """Check whether translation dependencies are ready.

    Returns a tuple ``(ok, reason)`` where ``ok`` is ``True`` when translation
    can run. When ``ok`` is ``False`` the ``reason`` contains a short
    human-readable explanation.
    """

    return False, "Translation support has been removed from jp2subs; use an external translator."


console = Console()

TRANSLATION_PROMPT = """
You are a professional Japanese-to-{target_lang} subtitle translator for anime.
- Keep absolute fidelity to what was spoken; do not omit interjections or verbal tics.
- Maintain repetitions and hesitations unless they are obvious noise.
- Preserve names and honorifics as-is unless a glossary override exists.
- Avoid over-correcting grammar; keep natural but faithful phrasing.
- Do not add or invent any meaning.
Translate each segment separately but keep coherent tone across the block.
Return one translation per input line, in the same order.
"""

POSTEDIT_PROMPT = """
You are refining a machine-translated draft.
Guidelines:
- Keep fidelity to the Japanese original; do not delete fillers or tics like えっと, あの.
- Keep names/honorifics unchanged unless a glossary enforces a replacement.
- Output natural {target_lang}, concise but accurate.
- Return the same number of lines you received, one translation per line.
"""

NORMALIZE_PROMPT = """
You gently normalize Japanese text for transcription cleanup.
- Do NOT rewrite content; preserve hesitations and repetitions.
- Output the same number of lines as input.
"""


class TranslationProvider:
    """Base class for pluggable translation providers."""

    def translate_block(
        self,
        lines: Sequence[str],
        source_lang: str,
        target_lang: str,
        glossary: Dict[str, str] | None = None,
        *,
        register_subprocess: Callable[[subprocess.Popen], None] | None = None,
        check_cancelled: Callable[[], bool] | None = None,
    ) -> List[str]:
        raise NotImplementedError


@dataclass
class EchoProvider(TranslationProvider):
    """Fallback provider that returns the source text."""

    def translate_block(
        self,
        lines: Sequence[str],
        source_lang: str,
        target_lang: str,
        glossary: Dict[str, str] | None = None,
        *,
        register_subprocess: Callable[[subprocess.Popen], None] | None = None,
        check_cancelled: Callable[[], bool] | None = None,
    ) -> List[str]:
        return list(lines)


@dataclass
class LocalLlamaCPPProvider(TranslationProvider):
    binary_path: str
    model_path: str

    def translate_block(
        self,
        lines: Sequence[str],
        source_lang: str,
        target_lang: str,
        glossary: Dict[str, str] | None = None,
        *,
        register_subprocess: Callable[[subprocess.Popen], None] | None = None,
        check_cancelled: Callable[[], bool] | None = None,
    ) -> List[str]:  # pragma: no cover - relies on external binary
        prompt = TRANSLATION_PROMPT.format(target_lang=target_lang)
        glossary_hint = "\n".join(f"{k} -> {v}" for k, v in (glossary or {}).items())
        joined = "\n".join(lines)
        output_format = (
            "Return one translation per input line, each prefixed with its 0-based line number "
            "and a tab character (example: `0\t<translation>`)."
        )

        if _env_truthy(os.getenv("JP2SUBS_LLAMA_CHAT")):
            full_prompt = (
                f"<system>\n{prompt.strip()}\n{output_format}\n</system>\n"
                f"<user>\nGlossary:\n{glossary_hint}\nINPUT:\n{joined}\nOUTPUT:\n</user>"
            )
        else:
            full_prompt = (
                f"{prompt}\n{output_format}\nGlossary:\n{glossary_hint}\nINPUT:\n{joined}\nOUTPUT:"
            ).strip()

        llama_args = shlex.split(os.getenv("JP2SUBS_LLAMA_ARGS", ""))
        cmd = [self.binary_path, "-m", self.model_path, *llama_args, "-p", full_prompt]
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        if register_subprocess:
            register_subprocess(proc)
        stdout_chunks: list[str] = []
        while True:
            try:
                stdout, _ = proc.communicate(timeout=0.5)
                stdout_chunks.append(stdout)
                break
            except subprocess.TimeoutExpired:
                if check_cancelled and check_cancelled():
                    proc.terminate()
                    try:
                        proc.wait(timeout=2)
                    except subprocess.TimeoutExpired:
                        proc.kill()
                    raise RuntimeError("Job cancelled")
                continue
        if proc.returncode != 0:
            raise RuntimeError(f"llama.cpp exited with code {proc.returncode}")
        output_lines = _parse_llama_output("".join(stdout_chunks).splitlines(), len(lines))
        return output_lines


@dataclass
class GenericAPIProvider(TranslationProvider):
    api_url: str
    api_key: str | None = None

    def translate_block(
        self,
        lines: Sequence[str],
        source_lang: str,
        target_lang: str,
        glossary: Dict[str, str] | None = None,
        *,
        register_subprocess: Callable[[subprocess.Popen], None] | None = None,
        check_cancelled: Callable[[], bool] | None = None,
    ) -> List[str]:  # pragma: no cover - network
        import requests

        payload = {
            "source_lang": source_lang,
            "target_lang": target_lang,
            "lines": list(lines),
            "prompt": TRANSLATION_PROMPT.format(target_lang=target_lang),
            "glossary": glossary or {},
        }
        headers = {"Authorization": f"Bearer {self.api_key}"} if self.api_key else {}
        response = requests.post(self.api_url, json=payload, headers=headers, timeout=120)
        response.raise_for_status()
        data = response.json()
        return list(data.get("translations", []))


def _parse_llama_output(lines: Sequence[str], expected_len: int) -> List[str]:
    outputs: List[str] = ["" for _ in range(expected_len)]
    for raw_line in lines:
        line = raw_line.strip()
        if not line or "\t" not in line:
            continue
        idx_str, text = line.split("\t", 1)
        try:
            idx = int(idx_str)
        except ValueError:
            continue
        if 0 <= idx < expected_len:
            outputs[idx] = text.strip()
    return outputs


def _env_truthy(value: str | None) -> bool:
    if value is None:
        return False
    return value.strip().lower() in {"1", "true", "yes", "on"}


def translate_document(
    doc: MasterDocument,
    target_langs: Iterable[str],
    mode: str = "llm",
    provider: str = "echo",
    block_size: int = 20,
    glossary: Dict[str, str] | None = None,
    *,
    on_progress: Callable[[ProgressEvent], None] | None = None,
    is_cancelled: Callable[[], bool] | None = None,
    register_subprocess: Callable[[subprocess.Popen], None] | None = None,
) -> MasterDocument:
    raise RuntimeError(
        "Translation support has been removed from jp2subs. Use a local LLM, DeepL, or ChatGPT to translate transcripts."
    )

    # The logic below is intentionally unreachable but preserved for reference.
    provider_impl = _provider_from_name(provider)
    langs = list(target_langs)
    total_blocks = sum((len(doc.segments) + block_size - 1) // block_size for _ in langs)
    completed_blocks = 0

    for lang in langs:
        console.log(f"Translating to {lang} using mode={mode} provider={provider}...")
        completed_blocks = _translate_lang(
            doc,
            lang,
            provider_impl,
            block_size,
            glossary,
            mode,
            total_blocks,
            completed_blocks,
            on_progress=on_progress,
            is_cancelled=is_cancelled,
            register_subprocess=register_subprocess,
        )
    return doc


def _translate_lang(
    doc: MasterDocument,
    target_lang: str,
    provider_impl: TranslationProvider,
    block_size: int,
    glossary: Dict[str, str] | None,
    mode: str,
    total_blocks: int,
    completed_blocks: int,
    *,
    on_progress: Callable[[ProgressEvent], None] | None = None,
    is_cancelled: Callable[[], bool] | None = None,
    register_subprocess: Callable[[subprocess.Popen], None] | None = None,
) -> int:
    doc.ensure_translation_key(target_lang)

    blocks_in_lang = (len(doc.segments) + block_size - 1) // block_size
    for block_index, start in enumerate(range(0, len(doc.segments), block_size), start=1):
        if is_cancelled and is_cancelled():
            raise RuntimeError("Job cancelled")
        block = doc.segments[start : start + block_size]
        source_lines = [seg.ja_raw for seg in block]
        draft = provider_impl.translate_block(
            source_lines,
            "ja",
            target_lang,
            glossary,
            register_subprocess=register_subprocess,
            check_cancelled=is_cancelled,
        )
        if mode.lower() == "draft+postedit":
            # Re-run on the draft to allow LLM post-editing while preserving fidelity.
            draft = provider_impl.translate_block(
                draft,
                "ja",
                target_lang,
                glossary,
                register_subprocess=register_subprocess,
                check_cancelled=is_cancelled,
            )
        for seg, text in zip(block, draft):
            seg.translations[target_lang] = text
        completed_blocks += 1
        if on_progress:
            percent = stage_percent("Translate", completed_blocks / max(1, total_blocks))
            detail = f"Block {block_index}/{blocks_in_lang} ({target_lang})"
            translated_count = start + len(block)
            detail += f" | Segments {translated_count}/{len(doc.segments)}"
            on_progress(ProgressEvent(stage="Translate", percent=percent, message="Translating...", detail=detail))
    if on_progress:
        on_progress(ProgressEvent(stage="Translate", percent=stage_percent("Translate", 1), message="Translation complete"))
    return completed_blocks


def _provider_from_name(name: str) -> TranslationProvider:
    name = name.lower()
    if name == "echo":
        return EchoProvider()
    if name == "local":
        cfg = _load_config()
        binary_path = _normalize_path(os.getenv("JP2SUBS_LLAMA_BINARY") or (cfg.translation.llama_binary if cfg else None))
        model_path = _normalize_path(os.getenv("JP2SUBS_LLAMA_MODEL") or (cfg.translation.llama_model if cfg else None))
        binary = str(binary_path) if binary_path else os.getenv("JP2SUBS_LLAMA_BINARY", "llama.exe")
        model = str(model_path) if model_path else os.getenv("JP2SUBS_LLAMA_MODEL", "model.gguf")
        return LocalLlamaCPPProvider(binary_path=binary, model_path=model)
    if name == "api":
        cfg = _load_config()
        url = os.getenv("JP2SUBS_API_URL") or (cfg.translation.api_url if cfg else "")
        if not url:
            raise RuntimeError("JP2SUBS_API_URL is required for api provider")
        key = os.getenv("JP2SUBS_API_KEY") or (cfg.translation.api_key if cfg else None)
        return GenericAPIProvider(api_url=url, api_key=key)
    return EchoProvider()

