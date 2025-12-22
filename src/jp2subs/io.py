"""Utilities to persist and load jp2subs master documents."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .models import MasterDocument


DEFAULT_MASTER_NAME = "master.json"


def load_master(path: str | Path) -> MasterDocument:
    data = Path(path).read_text(encoding="utf-8")
    parsed = json.loads(data)
    return MasterDocument.from_dict(parsed)


def save_master(doc: MasterDocument, path: str | Path) -> None:
    Path(path).write_text(json.dumps(doc.to_dict(), indent=2, ensure_ascii=False), encoding="utf-8")


def ensure_workdir(workdir: str | Path) -> Path:
    workdir_path = Path(workdir)
    workdir_path.mkdir(parents=True, exist_ok=True)
    return workdir_path


def master_path_from_workdir(workdir: str | Path) -> Path:
    return ensure_workdir(workdir) / DEFAULT_MASTER_NAME


def load_or_create_master(workdir: str | Path, source: str, meta_settings: dict[str, Any] | None = None) -> MasterDocument:
    path = master_path_from_workdir(workdir)
    if path.exists():
        return load_master(path)
    return MasterDocument.from_dict({"meta": {"source": source, "settings": meta_settings or {}, "tool_versions": {}}})

