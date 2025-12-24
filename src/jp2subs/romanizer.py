"""Romanization utilities using pykakasi."""
from __future__ import annotations

from typing import Callable, List

from pykakasi import kakasi

from .models import MasterDocument
from .progress import ProgressEvent, stage_percent


def romanize_segments(
    doc: MasterDocument,
    *,
    on_progress: Callable[[ProgressEvent], None] | None = None,
) -> MasterDocument:
    converter = kakasi()
    converter.setMode("H", "a")
    converter.setMode("K", "a")
    converter.setMode("J", "a")
    converter.setMode("s", True)
    conv = converter.getConverter()

    romaji_list: List[str] = []
    for seg in doc.segments:
        romaji = conv.do(seg.ja_raw)
        romaji_list.append(romaji)
    doc.add_romaji(romaji_list)
    if on_progress:
        on_progress(ProgressEvent(stage="Romanize", percent=stage_percent("Romanize", 1), message="Romanization complete"))
    return doc
