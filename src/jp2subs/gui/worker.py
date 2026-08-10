"""Backwards-compatible aliases for the workers module.

The workers moved to :mod:`jp2subs.gui.workers` when download and update jobs
were added. This shim keeps older imports working.
"""
from __future__ import annotations

from .workers import (  # noqa: F401
    ComponentInstallWorker,
    DownloadSignals,
    FinalizeWorker,
    PipelineWorker,
    UpdateCheckWorker,
    UpdateDownloadWorker,
    UpdateSignals,
    WorkerSignals,
)

__all__ = [
    "ComponentInstallWorker",
    "DownloadSignals",
    "FinalizeWorker",
    "PipelineWorker",
    "UpdateCheckWorker",
    "UpdateDownloadWorker",
    "UpdateSignals",
    "WorkerSignals",
]
