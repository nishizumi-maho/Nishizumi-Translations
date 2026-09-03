"""Measuring a recording, instead of guessing what it needs.

Every piece of advice about meeting audio — level it, do not denoise it, this
one is beyond saving — is really a claim about numbers that FFmpeg can just
report. One pass over the file gives the loudness, how far apart the loud and
quiet passages are, and whether the recorder clipped. From those three the app
can say what will help rather than offering the user a row of switches and a
shrug.
"""
from __future__ import annotations

import json
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

from .media import MediaError, ffmpeg_binary

#: Below this, a recording is quiet enough that levelling clearly helps.
#: Broadcast targets sit at -23 LUFS; speech much under -30 is faint.
QUIET_LUFS = -30.0

#: Loudness range, in loudness units. A meeting where everyone sits the same
#: distance from the recorder lands near 6; past this, some voices are far
#: enough away that a single gain for the whole file cannot serve both.
WIDE_RANGE_LU = 12.0

#: True peak at or above this means samples were squared off on the way in.
CLIPPED_DBTP = -0.1


@dataclass
class Measurement:
    """What one pass of FFmpeg found in the recording."""

    #: Integrated loudness in LUFS. More negative is quieter.
    loudness: float | None = None
    #: Loudness range in LU: the spread between the quiet and loud passages.
    range_lu: float | None = None
    #: True peak in dBTP. Zero is the ceiling.
    peak_dbtp: float | None = None
    #: Samples that hit the ceiling, as reported by astats.
    peak_count: int = 0
    #: Total samples, to turn the peak count into a proportion.
    samples: int = 0

    @property
    def clipped_share(self) -> float:
        return (self.peak_count / self.samples) if self.samples else 0.0

    @property
    def quiet(self) -> bool:
        return self.loudness is not None and self.loudness < QUIET_LUFS

    @property
    def wide_range(self) -> bool:
        return self.range_lu is not None and self.range_lu > WIDE_RANGE_LU

    @property
    def clipped(self) -> bool:
        if self.peak_dbtp is not None and self.peak_dbtp >= CLIPPED_DBTP:
            return True
        return self.clipped_share > 0.001


@dataclass
class Advice:
    """What the numbers mean, and what to switch on because of them."""

    lines: list[str]
    recommend_level: bool = False
    recommend_dynamic: bool = False


def measure(path: str | Path, *, timeout: int = 900) -> Measurement:
    """Run the analysis pass. Raises :class:`MediaError` when FFmpeg cannot."""

    path = Path(path)
    if not path.exists():
        raise MediaError(f"Arquivo não encontrado: {path}")

    command = [
        ffmpeg_binary(),
        "-hide_banner",
        "-nostats",
        "-i",
        str(path),
        "-af",
        "astats=metadata=1:reset=0,loudnorm=print_format=json",
        "-f",
        "null",
        "-",
    ]
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=timeout)
    except (OSError, subprocess.SubprocessError) as exc:
        raise MediaError(f"Não foi possível analisar o áudio: {exc}") from exc

    report = (result.stderr or "") + (result.stdout or "")
    if result.returncode != 0 and "loudnorm" not in report:
        raise MediaError("O FFmpeg não conseguiu ler este arquivo.")
    return _parse(report)


def _parse(report: str) -> Measurement:
    found = Measurement()

    block = _last_json_object(report)
    if block:
        found.loudness = _number(block.get("input_i"))
        found.range_lu = _number(block.get("input_lra"))
        found.peak_dbtp = _number(block.get("input_tp"))

    peaks = re.findall(r"Peak count:\s*([0-9.]+)", report)
    samples = re.findall(r"Number of samples:\s*([0-9]+)", report)
    if peaks:
        found.peak_count = int(float(peaks[-1]))
    if samples:
        found.samples = int(samples[-1])
    return found


def _last_json_object(report: str) -> dict | None:
    """The loudnorm summary, which FFmpeg prints as the last JSON in stderr."""

    start = report.rfind("{")
    end = report.rfind("}")
    if start < 0 or end < start:
        return None
    try:
        parsed = json.loads(report[start : end + 1])
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


def _number(value: object) -> float | None:
    try:
        number = float(str(value))
    except (TypeError, ValueError):
        return None
    # loudnorm reports -inf for silence, which is a measurement of nothing.
    return None if number != number or abs(number) > 1e6 else number


def advise(found: Measurement) -> Advice:
    """Turn the measurements into what to do about them."""

    lines: list[str] = []
    level = True
    dynamic = False

    if found.loudness is None:
        return Advice(
            lines=["Não deu para medir esta gravação. Os ajustes padrão servem."],
            recommend_level=True,
        )

    lines.append(f"Volume médio: {found.loudness:.1f} LUFS")
    if found.quiet:
        lines.append("  Gravação baixa — equalizar o volume vai ajudar bastante.")
    elif found.loudness > -14:
        lines.append("  Gravação alta. Equalizar ainda vale, para não estourar.")
    else:
        lines.append("  Volume em faixa normal.")

    if found.range_lu is not None:
        lines.append(f"Faixa dinâmica: {found.range_lu:.1f} LU")
        if found.wide_range:
            dynamic = True
            lines.append(
                "  Diferença grande entre as vozes altas e baixas — provavelmente "
                "há gente longe do gravador."
            )
            lines.append("  Ligue o NIVELAMENTO DINÂMICO: é o caso que ele resolve.")
        else:
            lines.append("  As vozes estão em volumes parecidos; o nivelamento simples basta.")

    if found.peak_dbtp is not None:
        lines.append(f"Pico: {found.peak_dbtp:.1f} dBTP")
    if found.clipped:
        share = f" ({found.clipped_share:.1%} das amostras)" if found.clipped_share else ""
        lines.append(f"  Gravação ESTOURADA{share}.")
        lines.append(
            "  Nada recupera trecho estourado: a informação não foi gravada. "
            "Na próxima, baixe o ganho do aparelho."
        )

    return Advice(lines=lines, recommend_level=level, recommend_dynamic=dynamic)


def report(path: str | Path) -> tuple[Measurement, Advice]:
    found = measure(path)
    return found, advise(found)
