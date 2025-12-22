"""Data models for the jp2subs pipeline."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Dict, List, Optional


@dataclass
class Segment:
    """Represents a subtitleable speech segment."""

    id: int
    start: float
    end: float
    ja_raw: str
    romaji: Optional[str] = None
    translations: Dict[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.start < 0 or self.end < 0:
            raise ValueError("start/end must be non-negative")
        if self.end < self.start:
            raise ValueError("end must be greater than or equal to start")

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class Meta:
    source: str
    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    tool_versions: Dict[str, str] = field(default_factory=dict)
    settings: Dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class MasterDocument:
    """Root JSON document used across the pipeline."""

    meta: Meta
    segments: List[Segment]

    def ensure_translation_key(self, lang: str) -> None:
        for segment in self.segments:
            segment.translations.setdefault(lang, "")

    def add_romaji(self, romaji_list: List[str]) -> None:
        if len(romaji_list) != len(self.segments):
            raise ValueError("Romaji list length mismatch with segments")
        for segment, romaji in zip(self.segments, romaji_list):
            segment.romaji = romaji

    def to_dict(self) -> dict:
        return {
            "meta": self.meta.to_dict(),
            "segments": [seg.to_dict() for seg in self.segments],
        }

    @classmethod
    def from_dict(cls, data: dict) -> "MasterDocument":
        meta = data.get("meta", {})
        meta_obj = Meta(
            source=meta.get("source", ""),
            created_at=meta.get("created_at", datetime.utcnow().isoformat()),
            tool_versions=meta.get("tool_versions", {}),
            settings=meta.get("settings", {}),
        )
        segments = []
        for seg in data.get("segments", []):
            segments.append(
                Segment(
                    id=int(seg.get("id", len(segments) + 1)),
                    start=float(seg.get("start", 0)),
                    end=float(seg.get("end", 0)),
                    ja_raw=str(seg.get("ja_raw", "")),
                    romaji=seg.get("romaji"),
                    translations=seg.get("translations", {}),
                )
            )
        return cls(meta=meta_obj, segments=segments)

