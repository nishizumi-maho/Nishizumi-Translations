"""Configuration helpers for jp2subs."""
from __future__ import annotations

import json
import os
import re
import shutil
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path
from typing import Any, Dict


def _app_config_dir() -> Path:
    """Return the default configuration directory.

    On Windows we prefer %APPDATA%/jp2subs, otherwise ~/.config/jp2subs.
    """

    appdata = os.environ.get("APPDATA")
    if appdata:
        return Path(appdata) / "jp2subs"
    return Path.home() / ".config" / "jp2subs"


def default_config_path() -> Path:
    return _app_config_dir() / "config.toml"


def app_config_dir() -> Path:
    """Public accessor for the jp2subs configuration directory."""

    return _app_config_dir()


@dataclass
class TranslationConfig:
    mode: str = "disabled"
    provider: str = "external"
    target_languages: list[str] = field(default_factory=list)
    api_url: str | None = None
    api_key: str | None = None
    llama_binary: str | None = None
    llama_model: str | None = None


@dataclass
class DefaultsConfig:
    model_size: str = "large-v3"
    beam_size: int = 5
    vad: bool = True
    mono: bool = False
    subtitle_format: str = "srt"
    best_of: int | None = None
    patience: float | None = None
    length_penalty: float | None = None
    word_timestamps: bool = True
    threads: int | None = None
    compute_type: str | None = None
    suppress_blank: bool = False
    suppress_tokens: int = -1
    extra_asr_args: dict[str, str] | None = None


@dataclass
class AppConfig:
    ffmpeg_path: str | None = None
    translation: TranslationConfig = field(default_factory=TranslationConfig)
    defaults: DefaultsConfig = field(default_factory=DefaultsConfig)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "AppConfig":
        translation = _filter_dataclass_fields(TranslationConfig, data.get("translation", {}))
        defaults = _filter_dataclass_fields(DefaultsConfig, data.get("defaults", {}))
        return cls(
            ffmpeg_path=data.get("ffmpeg_path"),
            translation=TranslationConfig(**translation),
            defaults=DefaultsConfig(**defaults),
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "ffmpeg_path": self.ffmpeg_path,
            "translation": asdict(self.translation),
            "defaults": asdict(self.defaults),
        }


def detect_ffmpeg(configured_path: str | None = None) -> str | None:
    """Return the ffmpeg binary path if available."""

    if configured_path:
        return configured_path
    return shutil.which("ffmpeg")


def detect_ffprobe(configured_ffmpeg_path: str | None = None) -> str | None:
    """Return the ffprobe binary path, preferring the configured ffmpeg folder."""

    if configured_ffmpeg_path:
        ffmpeg_path = Path(configured_ffmpeg_path)
        candidate_name = "ffprobe.exe" if ffmpeg_path.suffix.lower() == ".exe" else "ffprobe"
        sibling = ffmpeg_path.with_name(candidate_name)
        if sibling.exists():
            return str(sibling)
    return shutil.which("ffprobe")


def resolve_media_tool(binary: str) -> str:
    """Resolve ffmpeg/ffprobe through saved config while leaving other commands unchanged."""

    name = Path(binary).name.lower()
    if name not in {"ffmpeg", "ffmpeg.exe", "ffprobe", "ffprobe.exe"}:
        return binary

    cfg = load_config()
    if not cfg.ffmpeg_path:
        return binary
    if name in {"ffmpeg", "ffmpeg.exe"}:
        return detect_ffmpeg(cfg.ffmpeg_path) or binary
    return detect_ffprobe(cfg.ffmpeg_path) or binary


def load_config(path: Path | None = None) -> AppConfig:
    config_path = path or default_config_path()
    if not config_path.exists():
        return AppConfig()

    text = config_path.read_text(encoding="utf-8")
    # TOML is optional; fall back to JSON if needed.
    if text.strip().startswith("{"):
        data = json.loads(text)
    else:
        data = _parse_toml(text)

    return AppConfig.from_dict(data or {})


def save_config(config: AppConfig, path: Path | None = None) -> Path:
    config_path = path or default_config_path()
    config_path.parent.mkdir(parents=True, exist_ok=True)
    payload = config.to_dict()
    config_path.write_text(_to_toml(payload), encoding="utf-8")
    return config_path


def _parse_toml(raw: str) -> Dict[str, Any]:
    import tomllib

    try:
        return tomllib.loads(raw)
    except tomllib.TOMLDecodeError as exc:
        ffmpeg_match = re.search(r"^(ffmpeg_path\s*=\s*)\"([^\"]+)\"", raw, flags=re.MULTILINE)
        if not ffmpeg_match:
            raise

        escaped_path = ffmpeg_match.group(2).replace("\\", "\\\\")
        sanitized = raw[: ffmpeg_match.start(2)] + escaped_path + raw[ffmpeg_match.end(2) :]

        try:
            return tomllib.loads(sanitized)
        except tomllib.TOMLDecodeError:
            raise exc


def _to_toml(data: Dict[str, Any]) -> str:
    """Minimal TOML serializer to avoid extra dependencies."""

    lines: list[str] = []
    ffmpeg_path = data.get("ffmpeg_path")
    if ffmpeg_path:
        lines.append(f"ffmpeg_path = \"{_escape_basic_string(ffmpeg_path)}\"")

    translation = data.get("translation", {})
    defaults = data.get("defaults", {})

    lines.append("[translation]")
    for key, value in translation.items():
        if isinstance(value, list):
            serialized = ", ".join(f"\"{_escape_basic_string(item)}\"" for item in value)
            lines.append(f"{key} = [{serialized}]")
        elif value is not None:
            lines.append(f"{key} = \"{_escape_basic_string(value)}\"")

    lines.append("\n[defaults]")
    for key, value in defaults.items():
        if value is None:
            continue
        if isinstance(value, bool):
            literal = "true" if value else "false"
            lines.append(f"{key} = {literal}")
        elif isinstance(value, int):
            lines.append(f"{key} = {value}")
        elif isinstance(value, float):
            lines.append(f"{key} = {value}")
        elif isinstance(value, dict):
            inner = ", ".join(
                f"{inner_key} = \"{_escape_basic_string(str(inner_val))}\"" for inner_key, inner_val in value.items()
            )
            lines.append(f"{key} = {{{inner}}}")
        else:
            lines.append(f"{key} = \"{_escape_basic_string(value)}\"")

    return "\n".join(lines) + "\n"


def _escape_basic_string(value: str) -> str:
    """Escape backslashes and quotes for TOML basic strings."""

    return value.replace("\\", "\\\\").replace("\"", "\\\"")


def _filter_dataclass_fields(dataclass_type: type, data: Any) -> Dict[str, Any]:
    if not isinstance(data, dict):
        return {}
    allowed = {field.name for field in fields(dataclass_type)}
    return {key: value for key, value in data.items() if key in allowed}
