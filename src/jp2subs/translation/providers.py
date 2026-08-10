"""Translation back-ends.

Three engines share one interface:

* :class:`OfflineProvider` runs Meta's NLLB-200 locally through CTranslate2,
  which already ships with the app for speech recognition. No key, no network.
* :class:`DeepLProvider` and :class:`OpenAICompatibleProvider` call an external
  service with the user's own key, trading privacy for quality.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Protocol, Sequence

from ..runtime.download import post_form, post_json
from .languages import SOURCE, Language

CancelCheck = Callable[[], bool]

SUBTITLE_SYSTEM_PROMPT = (
    "You are a professional Japanese-to-{target} subtitle translator.\n"
    "Rules:\n"
    "- Translate each numbered line separately and return exactly the same numbering.\n"
    "- Keep the meaning faithful. Do not add, merge, split or omit lines.\n"
    "- Keep character names and honorifics (-san, -chan, -senpai) as they are.\n"
    "- Keep it short enough to read as a subtitle.\n"
    "- Reply with the numbered lines only, nothing else."
)


class Cancelled(RuntimeError):
    """Raised when a caller asks the run to stop."""


class Provider(Protocol):
    """Anything that can turn Japanese lines into another language."""

    name: str

    def translate(
        self,
        lines: Sequence[str],
        target: Language,
        *,
        is_cancelled: CancelCheck | None = None,
    ) -> list[str]:
        ...


def _check(is_cancelled: CancelCheck | None) -> None:
    if is_cancelled and is_cancelled():
        raise Cancelled("Job cancelled")


def _blank_safe(lines: Sequence[str]) -> tuple[list[str], list[int]]:
    """Split out non-empty lines so engines never see empty input."""

    payload: list[str] = []
    indexes: list[int] = []
    for index, line in enumerate(lines):
        if line and line.strip():
            payload.append(line.strip())
            indexes.append(index)
    return payload, indexes


@dataclass
class OfflineProvider:
    """NLLB-200 through CTranslate2, entirely on this machine."""

    model_dir: Path
    device: str = "auto"
    compute_type: str = "auto"
    beam_size: int = 4
    name: str = "offline"
    _translator: object | None = field(default=None, init=False, repr=False)
    _tokenizer: object | None = field(default=None, init=False, repr=False)

    def _load(self) -> tuple[object, object]:
        if self._translator is not None and self._tokenizer is not None:
            return self._translator, self._tokenizer

        try:
            import ctranslate2
            from tokenizers import Tokenizer
        except ImportError as exc:  # pragma: no cover - bundled with the app
            raise RuntimeError(
                "Offline translation needs ctranslate2 and tokenizers. Install them with "
                "'pip install \"jp2subs[asr]\"', or use the packaged build which bundles both."
            ) from exc

        model_dir = Path(self.model_dir)
        tokenizer_path = model_dir / "tokenizer.json"
        if not tokenizer_path.exists():
            raise RuntimeError(f"The translation model at {model_dir} has no tokenizer.json.")

        device = self.device
        if device == "auto":
            device = "cuda" if _cuda_available() else "cpu"
        compute_type = self.compute_type
        if compute_type == "auto":
            compute_type = "float16" if device == "cuda" else "int8"

        try:
            translator = ctranslate2.Translator(str(model_dir), device=device, compute_type=compute_type)
        except Exception:
            if device == "cpu":
                raise
            translator = ctranslate2.Translator(str(model_dir), device="cpu", compute_type="int8")

        self._translator = translator
        self._tokenizer = Tokenizer.from_file(str(tokenizer_path))
        return self._translator, self._tokenizer

    def unload(self) -> None:
        """Release the model so a long queue does not hold gigabytes of RAM."""

        self._translator = None
        self._tokenizer = None

    def translate(
        self,
        lines: Sequence[str],
        target: Language,
        *,
        is_cancelled: CancelCheck | None = None,
    ) -> list[str]:
        _check(is_cancelled)
        payload, indexes = _blank_safe(lines)
        results = [""] * len(lines)
        if not payload:
            return results

        translator, tokenizer = self._load()
        batch = [tokenizer.encode(line).tokens for line in payload]

        outputs = translator.translate_batch(
            batch,
            target_prefix=[[target.nllb]] * len(batch),
            beam_size=self.beam_size,
            max_batch_size=16,
            no_repeat_ngram_size=3,
        )

        for position, output in zip(indexes, outputs):
            tokens = list(output.hypotheses[0])
            if tokens and tokens[0] == target.nllb:
                tokens = tokens[1:]
            ids = [tokenizer.token_to_id(token) for token in tokens]
            results[position] = tokenizer.decode([i for i in ids if i is not None]).strip()
        return results


def _cuda_available() -> bool:
    try:
        import ctranslate2

        return ctranslate2.get_cuda_device_count() > 0
    except Exception:  # pragma: no cover - depends on the machine
        return False


@dataclass
class DeepLProvider:
    """DeepL's REST API. Free keys end in ``:fx`` and use a different host."""

    api_key: str
    name: str = "deepl"
    batch_size: int = 40

    @property
    def endpoint(self) -> str:
        host = "api-free.deepl.com" if self.api_key.strip().endswith(":fx") else "api.deepl.com"
        return f"https://{host}/v2/translate"

    def translate(
        self,
        lines: Sequence[str],
        target: Language,
        *,
        is_cancelled: CancelCheck | None = None,
    ) -> list[str]:
        if not self.api_key.strip():
            raise RuntimeError("A DeepL API key is required. Add one in Settings.")
        if not target.deepl:
            raise RuntimeError(f"DeepL does not offer {target.name}. Pick another language or engine.")

        payload, indexes = _blank_safe(lines)
        results = [""] * len(lines)
        if not payload:
            return results

        translated: list[str] = []
        for start in range(0, len(payload), self.batch_size):
            _check(is_cancelled)
            chunk = payload[start : start + self.batch_size]
            fields = [("target_lang", target.deepl), ("source_lang", SOURCE.deepl)]
            fields.extend(("text", line) for line in chunk)
            data = post_form(
                self.endpoint,
                fields,
                headers={"Authorization": f"DeepL-Auth-Key {self.api_key.strip()}"},
            )
            translated.extend(item.get("text", "") for item in data.get("translations", []))

        for position, text in zip(indexes, translated):
            results[position] = text.strip()
        return results


@dataclass
class OpenAICompatibleProvider:
    """Any OpenAI-style ``/chat/completions`` endpoint.

    Works with OpenAI, OpenRouter, and local servers such as LM Studio or
    Ollama, which is the route to genuinely good anime dialogue.
    """

    api_key: str = ""
    base_url: str = "https://api.openai.com/v1"
    model: str = "gpt-4o-mini"
    name: str = "openai"
    batch_size: int = 25
    temperature: float = 0.2

    @property
    def endpoint(self) -> str:
        return f"{self.base_url.rstrip('/')}/chat/completions"

    def translate(
        self,
        lines: Sequence[str],
        target: Language,
        *,
        is_cancelled: CancelCheck | None = None,
    ) -> list[str]:
        payload, indexes = _blank_safe(lines)
        results = [""] * len(lines)
        if not payload:
            return results

        translated: list[str] = []
        for start in range(0, len(payload), self.batch_size):
            _check(is_cancelled)
            chunk = payload[start : start + self.batch_size]
            translated.extend(self._translate_chunk(chunk, target))

        for position, text in zip(indexes, translated):
            results[position] = text.strip()
        return results

    def _translate_chunk(self, chunk: Sequence[str], target: Language) -> list[str]:
        numbered = "\n".join(f"{index + 1}. {line}" for index, line in enumerate(chunk))
        headers = {}
        if self.api_key.strip():
            headers["Authorization"] = f"Bearer {self.api_key.strip()}"

        data = post_json(
            self.endpoint,
            {
                "model": self.model,
                "temperature": self.temperature,
                "messages": [
                    {"role": "system", "content": SUBTITLE_SYSTEM_PROMPT.format(target=target.name)},
                    {"role": "user", "content": numbered},
                ],
            },
            headers=headers,
            timeout=180,
        )

        choices = data.get("choices") or []
        if not choices:
            raise RuntimeError(f"The translation endpoint returned no choices: {str(data)[:200]}")
        content = choices[0].get("message", {}).get("content", "")
        return parse_numbered(content, len(chunk))


def parse_numbered(content: str, expected: int) -> list[str]:
    """Pull ``1. text`` lines back out of a model reply.

    Falls back to plain line order when the model drops the numbering.
    """

    results = [""] * expected
    matched = False
    for raw in (content or "").splitlines():
        line = raw.strip()
        if not line:
            continue
        match = re.match(r"^(\d+)\s*[.)\]:-]\s*(.*)$", line)
        if not match:
            continue
        index = int(match.group(1)) - 1
        if 0 <= index < expected:
            results[index] = match.group(2).strip()
            matched = True

    if matched:
        return results

    plain = [line.strip() for line in (content or "").splitlines() if line.strip()]
    for index in range(min(expected, len(plain))):
        results[index] = plain[index]
    return results
