"""Translation orchestration for jp2subs."""
from __future__ import annotations

import os
import shlex
import subprocess
from dataclasses import dataclass
from typing import Dict, Iterable, List, Sequence

from rich.console import Console

from .models import MasterDocument

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
        self, lines: Sequence[str], source_lang: str, target_lang: str, glossary: Dict[str, str] | None = None
    ) -> List[str]:
        raise NotImplementedError


@dataclass
class EchoProvider(TranslationProvider):
    """Fallback provider that returns the source text."""

    def translate_block(
        self, lines: Sequence[str], source_lang: str, target_lang: str, glossary: Dict[str, str] | None = None
    ) -> List[str]:
        return list(lines)


@dataclass
class LocalLlamaCPPProvider(TranslationProvider):
    binary_path: str
    model_path: str

    def translate_block(
        self, lines: Sequence[str], source_lang: str, target_lang: str, glossary: Dict[str, str] | None = None
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
        result = subprocess.run(cmd, check=True, capture_output=True, text=True)
        output_lines = _parse_llama_output(result.stdout.splitlines(), len(lines))
        return output_lines


@dataclass
class GenericAPIProvider(TranslationProvider):
    api_url: str
    api_key: str | None = None

    def translate_block(
        self, lines: Sequence[str], source_lang: str, target_lang: str, glossary: Dict[str, str] | None = None
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
) -> MasterDocument:
    provider_impl = _provider_from_name(provider)

    for lang in target_langs:
        console.log(f"Translating to {lang} using mode={mode} provider={provider}...")
        _translate_lang(doc, lang, provider_impl, block_size, glossary, mode)
    return doc


def _translate_lang(
    doc: MasterDocument,
    target_lang: str,
    provider_impl: TranslationProvider,
    block_size: int,
    glossary: Dict[str, str] | None,
    mode: str,
) -> None:
    doc.ensure_translation_key(target_lang)

    for start in range(0, len(doc.segments), block_size):
        block = doc.segments[start : start + block_size]
        source_lines = [seg.ja_raw for seg in block]
        draft = provider_impl.translate_block(source_lines, "ja", target_lang, glossary)
        if mode.lower() == "draft+postedit":
            # Re-run on the draft to allow LLM post-editing while preserving fidelity.
            draft = provider_impl.translate_block(draft, "ja", target_lang, glossary)
        for seg, text in zip(block, draft):
            seg.translations[target_lang] = text


def _provider_from_name(name: str) -> TranslationProvider:
    name = name.lower()
    if name == "echo":
        return EchoProvider()
    if name == "local":
        binary = os.getenv("JP2SUBS_LLAMA_BINARY", "llama.exe")
        model = os.getenv("JP2SUBS_LLAMA_MODEL", "model.gguf")
        return LocalLlamaCPPProvider(binary_path=binary, model_path=model)
    if name == "api":
        url = os.getenv("JP2SUBS_API_URL", "")
        if not url:
            raise RuntimeError("JP2SUBS_API_URL is required for api provider")
        key = os.getenv("JP2SUBS_API_KEY")
        return GenericAPIProvider(api_url=url, api_key=key)
    return EchoProvider()

