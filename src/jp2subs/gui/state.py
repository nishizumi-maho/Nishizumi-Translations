"""Dataclasses describing GUI state and defaults."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import List

from ..config import AppConfig, DefaultsConfig, TranslationConfig, load_config, save_config


@dataclass
class PipelineJob:
    source: Path | None = None
    workdir: Path | None = None
    generate_romaji: bool = False
    fmt: str = "srt"
    beam_size: int = 5
    model_size: str = "large-v3"
    vad: bool = True
    mono: bool = False
    best_of: int | None = None
    patience: float | None = None
    length_penalty: float | None = None
    word_timestamps: bool = True
    threads: int | None = None
    compute_type: str | None = None
    extra_asr_args: dict | None = None


@dataclass
class FinalizeJob:
    video: Path | None = None
    subtitle: Path | None = None
    mode: str = "sidecar"
    out_dir: Path | None = None
    codec: str = "libx264"
    crf: int = 18
    preset: str = "slow"
    font: str | None = None
    font_size: int = 36
    bold: bool = False
    italic: bool = False
    outline: int = 2
    shadow: int = 1
    margin_v: int = 20
    alignment: int = 2
    primary_color: str = "&H00FFFFFF"
    background_enabled: bool = False
    background_color: str = "&H80000000"


def load_app_state() -> AppConfig:
    return load_config()


def persist_app_state(cfg: AppConfig) -> None:
    save_config(cfg)
