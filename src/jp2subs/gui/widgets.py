"""Backwards-compatible aliases for the pre-2.1 widget module.

The tabbed layout was replaced by a sidebar shell with one module per page.
These aliases keep older imports (and any external scripts) working.
"""
from __future__ import annotations

from .common import DropZone, FileQueue  # noqa: F401
from .main_window import MainWindow  # noqa: F401
from .pages.components import ComponentsPage  # noqa: F401
from .pages.finalize import FinalizePage  # noqa: F401
from .pages.settings import SettingsPage  # noqa: F401
from .pages.transcribe import STAGES, TranscribePage, parse_extra_args  # noqa: F401

#: Former tab classes, now full pages.
PipelineTab = TranscribePage
FinalizeTab = FinalizePage
SettingsTab = SettingsPage
#: The drop-enabled list used to be called this.
FileDropListWidget = FileQueue

__all__ = [
    "ComponentsPage",
    "DropZone",
    "FileDropListWidget",
    "FileQueue",
    "FinalizePage",
    "FinalizeTab",
    "MainWindow",
    "PipelineTab",
    "STAGES",
    "SettingsPage",
    "SettingsTab",
    "TranscribePage",
    "parse_extra_args",
]
