"""Telling the voices apart, with sherpa-onnx.

Two ONNX models do the work: pyannote segmentation finds where speech is and
where a voice changes, and CAM++ turns each stretch into a voice fingerprint
that gets clustered. Both are downloaded from the Components page; neither
needs an account, a token or a network connection at transcription time.
"""
from __future__ import annotations

from pathlib import Path
from typing import Callable

from jp2subs.runtime.manager import EMBEDDING_MODEL, SEGMENTATION_MODEL, manager

from .model import SpeakerSpan
from .progress import ProgressEvent, stage_percent

#: Catalog key of the pack this module loads.
COMPONENT_KEY = "diarize:sherpa-cam++"

#: How close two stretches of speech have to sound to be counted as one person.
#: Higher merges similar voices, lower splits them.
DEFAULT_THRESHOLD = 0.5
#: The choices the UI offers, phrased by the symptom they fix.
THRESHOLD_CHOICES: tuple[tuple[str, float], ...] = (
    ("Automática", DEFAULT_THRESHOLD),
    ("Separar mais (vozes parecidas viraram uma só)", 0.35),
    ("Juntar mais (uma pessoa virou duas)", 0.7),
)


class DiarizationUnavailable(RuntimeError):
    """The models or the sherpa-onnx runtime are missing.

    Raised rather than returning nothing so the caller can decide: the pipeline
    keeps the transcript and drops the speaker labels.
    """


def models_installed() -> bool:
    return manager.is_installed(COMPONENT_KEY)


def runtime_available() -> bool:
    """True when the sherpa-onnx Python package can be imported."""

    try:
        import sherpa_onnx  # noqa: F401
    except Exception:  # pragma: no cover - optional dependency
        return False
    return True


def is_available() -> bool:
    return models_installed() and runtime_available()


def unavailable_reason() -> str:
    """Why speaker identification is off, phrased for the user. Empty when it is on."""

    if not runtime_available():
        return (
            "O componente de identificação de interlocutores não está disponível nesta "
            'instalação (sherpa-onnx ausente). Instale com: pip install "reuniao[interlocutores]"'
        )
    if not models_installed():
        return (
            "Os modelos de identificação de interlocutores ainda não foram baixados. "
            "Baixe-os na página Componentes."
        )
    return ""


def model_paths() -> tuple[Path, Path]:
    """Folders resolved to the segmentation and embedding graphs."""

    root = manager.install_path(_component())
    segmentation = root / SEGMENTATION_MODEL
    embedding = root / EMBEDDING_MODEL
    if not segmentation.exists() or not embedding.exists():
        raise DiarizationUnavailable(unavailable_reason() or "Modelos de interlocutores incompletos.")
    return segmentation, embedding


def diarize(
    samples,
    *,
    threshold: float = DEFAULT_THRESHOLD,
    threads: int = 0,
    on_progress: Callable[[ProgressEvent], None] | None = None,
    is_cancelled: Callable[[], bool] | None = None,
) -> list[SpeakerSpan]:
    """Split 16 kHz mono *samples* into per-voice spans.

    How many people are in the room is worked out from *threshold* rather than
    stated up front: raise it and similar voices merge, lower it and they split.
    """

    try:
        import sherpa_onnx
    except Exception as exc:  # pragma: no cover - optional dependency
        raise DiarizationUnavailable(unavailable_reason()) from exc

    segmentation, embedding = model_paths()
    config = sherpa_onnx.OfflineSpeakerDiarizationConfig(
        segmentation=sherpa_onnx.OfflineSpeakerSegmentationModelConfig(
            pyannote=sherpa_onnx.OfflineSpeakerSegmentationPyannoteModelConfig(
                model=str(segmentation)
            ),
            num_threads=threads or 2,
        ),
        embedding=sherpa_onnx.SpeakerEmbeddingExtractorConfig(
            model=str(embedding), num_threads=threads or 2
        ),
        # num_clusters is deliberately left at -1, which is what makes the
        # threshold the deciding knob. Pinning it to a known headcount reads
        # like the better option and measures worse: on a two-voice recording
        # that auto mode splits correctly, asking for 2 returns 1, and asking
        # for 4 on a four-voice one returns 3, at any threshold. The threshold
        # in auto mode behaves the way you would expect instead — on that same
        # four-voice recording it walks 8 voices at 0.2 down to 4 at 0.6.
        clustering=sherpa_onnx.FastClusteringConfig(
            num_clusters=-1,
            threshold=float(threshold),
        ),
        min_duration_on=0.3,
        min_duration_off=0.5,
    )
    if not config.validate():
        raise DiarizationUnavailable("A configuração de identificação de interlocutores é inválida.")

    engine = sherpa_onnx.OfflineSpeakerDiarization(config)

    def report(done: int, total: int) -> int:
        # Returning non-zero asks sherpa-onnx to stop early.
        if is_cancelled and is_cancelled():
            return 1
        if on_progress and total:
            on_progress(
                ProgressEvent(
                    stage="Interlocutores",
                    percent=stage_percent("Interlocutores", done / total),
                    message="Identificando os interlocutores...",
                    detail=f"{int(done * 100 / total)}% do áudio analisado",
                )
            )
        return 0

    result = engine.process(samples, callback=report)
    if is_cancelled and is_cancelled():
        raise DiarizationUnavailable("Identificação de interlocutores cancelada.")

    return renumber(
        SpeakerSpan(start=float(item.start), end=float(item.end), speaker=int(item.speaker))
        for item in result.sort_by_start_time()
    )


def renumber(spans) -> list[SpeakerSpan]:
    """Relabel voices 0, 1, 2... in the order they first speak.

    The clustering hands back arbitrary cluster ids — a two-person recording
    can come back as speakers 0 and 3 — which would read strangely as
    "Interlocutor 1" and "Interlocutor 4" in the transcript.
    """

    ordered = sorted(spans, key=lambda item: (item.start, item.end))
    mapping: dict[int, int] = {}
    result: list[SpeakerSpan] = []
    for span in ordered:
        if span.speaker not in mapping:
            mapping[span.speaker] = len(mapping)
        result.append(SpeakerSpan(start=span.start, end=span.end, speaker=mapping[span.speaker]))
    return result


def _component():
    from jp2subs.runtime import catalog

    item = catalog.component(COMPONENT_KEY)
    if item is None:  # pragma: no cover - the key is a constant in the catalog
        raise DiarizationUnavailable("O pacote de interlocutores não está no catálogo.")
    return item
