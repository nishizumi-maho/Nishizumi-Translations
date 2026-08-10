"""Search Hugging Face for Whisper models the app can actually load.

The catalog ships a curated list, but new Whisper releases and community
fine-tunes appear constantly. Anything published in CTranslate2 format works
here without the app needing an update.
"""
from __future__ import annotations

import urllib.parse
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field

from .download import fetch_json, remote_size

API = "https://huggingface.co/api/models"
RESOLVE = "https://huggingface.co/{repo}/resolve/main/{path}"

#: A CTranslate2 model directory is recognised by these two files.
REQUIRED_FILES = ("model.bin", "config.json")

#: Suggestions offered before the user types anything.
SUGGESTED_QUERIES = (
    "faster-whisper",
    "whisper japanese",
    "faster-whisper turbo",
    "kotoba-whisper",
    "whisper anime",
    "ct2 whisper",
)


@dataclass
class SearchResult:
    """One repository returned by a search."""

    repo_id: str
    downloads: int = 0
    likes: int = 0
    last_modified: str = ""
    files: tuple[str, ...] = field(default_factory=tuple)
    size: int = 0
    tags: tuple[str, ...] = field(default_factory=tuple)

    @property
    def owner(self) -> str:
        return self.repo_id.split("/", 1)[0] if "/" in self.repo_id else ""

    @property
    def name(self) -> str:
        return self.repo_id.split("/")[-1]

    @property
    def is_loadable(self) -> bool:
        return all(name in self.files for name in REQUIRED_FILES)


def _to_result(payload: dict) -> SearchResult:
    siblings = payload.get("siblings") or []
    return SearchResult(
        repo_id=str(payload.get("modelId") or payload.get("id") or ""),
        downloads=int(payload.get("downloads") or 0),
        likes=int(payload.get("likes") or 0),
        last_modified=str(payload.get("lastModified") or "")[:10],
        files=tuple(str(item.get("rfilename", "")) for item in siblings),
        tags=tuple(str(tag) for tag in (payload.get("tags") or [])),
    )


def _model_size(result: SearchResult) -> int:
    """Weight file size, which is effectively the whole download."""

    return remote_size(RESOLVE.format(repo=result.repo_id, path="model.bin"))


def _fill_sizes(results: list[SearchResult]) -> None:
    if not results:
        return
    with ThreadPoolExecutor(max_workers=8) as pool:
        for result, size in zip(results, pool.map(_model_size, results)):
            result.size = size


def search_models(query: str, *, limit: int = 20, with_sizes: bool = True) -> list[SearchResult]:
    """Return CTranslate2-compatible models matching ``query``.

    ``full=true`` makes Hugging Face include each repository's file list in the
    search response, so one request is enough to tell whether a model is usable.
    """

    text = (query or "").strip()
    if not text:
        text = "faster-whisper"

    params = {
        "search": text,
        "limit": max(limit * 3, 30),
        "full": "true",
        "sort": "downloads",
        "direction": -1,
    }
    payloads = fetch_json(f"{API}?{urllib.parse.urlencode(params)}")
    if not isinstance(payloads, list):  # pragma: no cover - defensive
        return []

    results = [_to_result(item) for item in payloads]
    usable = [item for item in results if item.repo_id and item.is_loadable][:limit]

    if with_sizes:
        _fill_sizes(usable)
    return usable


def inspect_repo(repo_id: str, *, with_size: bool = True) -> SearchResult | None:
    """Look up one repository by name, for when the user pastes an id directly."""

    cleaned = (repo_id or "").strip().strip("/")
    if not cleaned:
        return None
    if cleaned.startswith("http"):
        # Accept a pasted URL such as https://huggingface.co/owner/name
        parts = [part for part in urllib.parse.urlparse(cleaned).path.split("/") if part]
        cleaned = "/".join(parts[:2])
    if "/" not in cleaned:
        return None

    try:
        payload = fetch_json(f"{API}/{cleaned}")
    except Exception:
        return None

    payload.setdefault("modelId", cleaned)
    result = _to_result(payload)
    if with_size and result.is_loadable:
        result.size = _model_size(result)
    return result
