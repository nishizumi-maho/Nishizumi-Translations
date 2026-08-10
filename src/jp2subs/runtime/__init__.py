"""Self-service runtime: everything jp2subs can download and install on its own.

The GUI and CLI both talk to :class:`~jp2subs.runtime.manager.ComponentManager`,
which knows how to fetch Whisper models, an ffmpeg build, and the CUDA runtime
libraries into a per-user data directory. Nothing here requires the user to run
pip, unzip an archive, or edit a PATH entry.
"""

from .catalog import (
    Component,
    ComponentKind,
    all_components,
    component,
    ffmpeg_component,
    models,
    recommended_model_key,
)
from .manager import ComponentManager, ComponentStatus
from .manager import manager as component_manager
from .store import data_dir, human_size, models_dir, tools_dir

# NOTE: the singleton is exported as ``component_manager`` on purpose — binding
# it to ``manager`` here would shadow the ``jp2subs.runtime.manager`` module.

__all__ = [
    "Component",
    "ComponentKind",
    "ComponentManager",
    "ComponentStatus",
    "all_components",
    "component",
    "component_manager",
    "data_dir",
    "ffmpeg_component",
    "human_size",
    "models",
    "models_dir",
    "recommended_model_key",
    "tools_dir",
]
