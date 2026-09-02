"""What this app offers to download, described in Portuguese.

The download machinery, the folder on disk and the record of what is installed
are all shared with the subtitle app — install a model in one and the other
sees it. Only the selection and the wording are ours: the Japanese fine-tunes
have no place here, and the speaker packs have no place there.
"""
from __future__ import annotations

from dataclasses import replace

from jp2subs.runtime import catalog, store
from jp2subs.runtime.catalog import Component, ComponentKind
from jp2subs.runtime.manager import manager

from .diarize import COMPONENT_KEY as DIARIZATION_KEY

#: Whisper models worth offering for Portuguese, best first in each size class.
#: The Japanese fine-tunes and the English distil model are left out on purpose.
_MODEL_COPY: dict[str, tuple[str, str]] = {
    "model:large-v3-turbo": (
        "Rápido e preciso. A melhor escolha para quase toda reunião.",
        "",
    ),
    "model:large-v3": (
        "A maior precisão disponível. Pede uma GPU, ou muita paciência no processador.",
        "Em uma reunião longa sem GPU, pode levar várias horas.",
    ),
    "model:large-v2": (
        "Geração anterior do modelo grande. Útil se o Large v3 errar nomes próprios.",
        "",
    ),
    "model:medium": (
        "Bom meio-termo quando não há GPU e a gravação tem ruído.",
        "",
    ),
    "model:small": (
        "Leve o bastante para rodar no processador com resultado aceitável.",
        "",
    ),
    "model:base": (
        "Rápido e pequeno. Serve para testar o aplicativo.",
        "Qualidade limitada: espere erros de acentuação e de nomes.",
    ),
    "model:tiny": (
        "O mais rápido de todos, com a menor qualidade.",
        "Só para testar se tudo está funcionando.",
    ),
}

#: Order the models appear on the page.
_MODEL_ORDER = (
    "model:large-v3-turbo",
    "model:large-v3",
    "model:large-v2",
    "model:medium",
    "model:small",
    "model:base",
    "model:tiny",
)


def _localize_model(item: Component) -> Component:
    summary, notes = _MODEL_COPY.get(item.key, (item.summary, item.notes))
    return replace(
        item,
        summary=summary,
        notes=notes,
        quality=_QUALITY_PT.get(item.quality, item.quality),
        speed=_SPEED_PT.get(item.speed, item.speed),
    )


_QUALITY_PT = {
    "Best": "Máxima qualidade",
    "Excellent": "Excelente",
    "Very good": "Muito boa",
    "Good": "Boa",
    "Basic": "Básica",
}

_SPEED_PT = {
    "Fastest": "Muito rápido",
    "Very fast": "Bem rápido",
    "Fast": "Rápido",
    "Moderate": "Moderado",
    "Slow": "Lento",
}


def models() -> tuple[Component, ...]:
    """Speech models, in the order the page should list them."""

    by_key = {item.key: item for item in catalog.models()}
    return tuple(_localize_model(by_key[key]) for key in _MODEL_ORDER if key in by_key)


def ffmpeg() -> Component:
    item = catalog.ffmpeg_component()
    return replace(
        item,
        name="FFmpeg",
        summary="Lê o arquivo de áudio ou de vídeo da reunião. O aplicativo não funciona sem ele.",
        notes="",
    )


def diarization() -> Component:
    item = catalog.component(DIARIZATION_KEY)
    if item is None:  # pragma: no cover - the key is a constant in the catalog
        raise RuntimeError("O pacote de interlocutores sumiu do catálogo.")
    return replace(
        item,
        name="Identificação de interlocutores",
        summary="Separa as vozes da gravação para marcar quem falou cada trecho.",
        notes="Funciona em qualquer idioma. Sem ele, a transcrição sai só com os horários.",
    )


def acceleration() -> Component | None:
    item = catalog.cuda_component()
    if item is None:
        return None
    return replace(
        item,
        name="Aceleração por GPU NVIDIA",
        summary="Bibliotecas cuBLAS e cuDNN que fazem a transcrição rodar na placa de vídeo.",
        notes="Só serve com placa NVIDIA e driver recente. Sem ela, tudo roda no processador.",
    )


def page_sections() -> list[tuple[str, str, tuple[Component, ...]]]:
    """(title, hint, items) for each block of the Components page."""

    sections: list[tuple[str, str, tuple[Component, ...]]] = [
        (
            "Essenciais",
            "O mínimo para transcrever: o leitor de mídia e um modelo de voz.",
            (ffmpeg(),),
        ),
        (
            "Modelos de transcrição",
            "Um basta. Quanto maior o modelo, melhor o texto e mais lenta a transcrição.",
            models(),
        ),
        (
            "Interlocutores",
            "Opcional, mas é o que faz a transcrição dizer quem falou.",
            (diarization(),),
        ),
    ]
    gpu = acceleration()
    if gpu:
        sections.append(
            ("Desempenho", "Opcional. Só faz diferença em computador com placa NVIDIA.", (gpu,))
        )
    return sections


def all_components() -> tuple[Component, ...]:
    return tuple(item for _title, _hint, items in page_sections() for item in items)


def installed_models() -> list[Component]:
    """Models already on disk, in page order, ready to transcribe with."""

    return [item for item in models() if manager.is_installed(item.key)]


def missing_essentials() -> list[Component]:
    """Components without which nothing can be transcribed."""

    missing: list[Component] = []
    tool = ffmpeg()
    if not manager.is_installed(tool.key) and not _ffmpeg_on_path():
        missing.append(tool)
    if not installed_models():
        recommended = next((item for item in models() if item.recommended), None)
        if recommended:
            missing.append(recommended)
    return missing


def is_ready() -> bool:
    return not missing_essentials()


def installed_size() -> int:
    return manager.total_size()


def human_size(num_bytes: float | None) -> str:
    return store.human_size(num_bytes)


def _ffmpeg_on_path() -> bool:
    import shutil

    return shutil.which("ffmpeg") is not None


__all__ = [
    "Component",
    "ComponentKind",
    "acceleration",
    "all_components",
    "diarization",
    "ffmpeg",
    "human_size",
    "installed_models",
    "installed_size",
    "is_ready",
    "missing_essentials",
    "models",
    "page_sections",
]
