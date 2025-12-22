"""Romanization utilities using pykakasi."""
from __future__ import annotations

from typing import List

from pykakasi import kakasi

from .models import MasterDocument


def romanize_segments(doc: MasterDocument) -> MasterDocument:
    converter = kakasi()
    converter.setMode("H", "a")
    converter.setMode("K", "a")
    converter.setMode("J", "a")
    conv = converter.getConverter()

    romaji_list: List[str] = []
    for seg in doc.segments:
        romaji = conv.do(seg.ja_raw)
        romaji_list.append(romaji)
    doc.add_romaji(romaji_list)
    return doc

