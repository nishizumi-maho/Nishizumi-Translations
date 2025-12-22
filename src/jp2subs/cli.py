"""Typer CLI for jp2subs."""
from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
from typing import List, Optional, Sequence

import typer
from rich.console import Console
from rich.progress import BarColumn, Progress, TaskProgressColumn, TextColumn

from . import __version__
from . import audio, asr, io, romanizer, subtitles, translation, video
from .models import MasterDocument

BATCH_STAGES: Sequence[str] = ("ingest", "transcribe", "romanize", "translate", "export")

app = typer.Typer(add_completion=False, help="jp2subs: end-to-end JP transcription, translation, and subtitling")
console = Console()


@app.callback()
def main(ctx: typer.Context):
    """jp2subs CLI entrypoint."""
    ctx.obj = {}


@app.command()
def ingest(input_path: Path, workdir: Path = typer.Option(Path("workdir")), mono: bool = False):
    """Prepare workdir and extract audio when a video is provided."""
    audio_path = audio.ingest_media(input_path, workdir, mono=mono)
    console.print(f"Audio ready at [bold]{audio_path}[/bold]")


@app.command()
def transcribe(
    input_path: Path,
    workdir: Path = typer.Option(Path("workdir")),
    model_size: str = "large-v3",
    device: Optional[str] = None,
    vad: bool = True,
    temperature: float = 0.0,
    beam_size: int = 5,
):
    """Run ASR and produce master.json and Japanese transcripts."""

    audio_path = input_path
    if audio.is_video(input_path):
        audio_path = audio.ingest_media(input_path, workdir)

    doc = asr.transcribe_audio(
        audio_path,
        model_size=model_size,
        vad_filter=vad,
        temperature=temperature,
        beam_size=beam_size,
        device=device,
    )
    master_path = io.master_path_from_workdir(workdir)
    io.save_master(doc, master_path)
    _write_transcripts(doc, workdir, prefix="transcript_ja", lang="ja")
    console.print(f"Master JSON saved to [bold]{master_path}[/bold]")


@app.command()
def romanize(master: Path, workdir: Path = typer.Option(Path("workdir"))):
    """Generate romaji from Japanese transcription."""
    doc = io.load_master(master)
    doc = romanizer.romanize_segments(doc)
    io.save_master(doc, master)
    _write_transcripts(doc, workdir, prefix="transcript_romaji", lang="ja", use_romaji=True)
    console.print("Romaji added to master and transcripts generated.")


@app.command()
def translate(
    master: Path,
    to: List[str] = typer.Option(..., help="Destination language codes e.g. pt-BR"),
    mode: str = typer.Option("llm", case_sensitive=False),
    provider: str = typer.Option("echo", help="Translation provider: echo|local|api"),
    block_size: int = 20,
    glossary: Optional[Path] = typer.Option(None, help="Optional glossary JSON mapping source->target"),
):
    """Translate segments to the requested languages."""

    doc = io.load_master(master)
    glossary_data = json.loads(glossary.read_text(encoding="utf-8")) if glossary else None
    doc = translation.translate_document(
        doc, target_langs=to, mode=mode, provider=provider, block_size=block_size, glossary=glossary_data
    )
    io.save_master(doc, master)
    console.print(f"Translations added to {master}")


@app.command()
def export(
    master: Path,
    fmt: str = typer.Option("srt", help="Subtitle format: srt|vtt|ass"),
    lang: str = typer.Option("pt-BR", help="Primary language code"),
    bilingual: Optional[str] = typer.Option(None, help="Secondary language code e.g. ja"),
    out: Optional[Path] = typer.Option(None, help="Output path; defaults to workdir/subs_<lang>.<fmt>"),
    workdir: Path = typer.Option(Path("workdir")),
):
    """Export subtitles for a given language and format."""

    doc = io.load_master(master)
    output_path = out or (Path(workdir) / f"subs_{lang}.{fmt}")
    subtitles.write_subtitles(doc, output_path, fmt, lang=lang, secondary=bilingual)
    console.print(f"Subtitle written to [bold]{output_path}[/bold]")


@app.command(name="mux-soft")
def mux_soft_cmd(video_path: Path, subs_path: Path, out: Path = typer.Option(Path("out.mkv"))):
    """Soft-mux subtitles into MKV without re-encoding."""
    result = video.mux_soft(video_path, subs_path, out)
    console.print(f"Muxed file at {result}")


@app.command()
def burn(
    video_path: Path,
    subs_path: Path,
    out: Path = typer.Option(Path("out_hard.mp4")),
    codec: str = "libx264",
    crf: int = 18,
    font: str | None = typer.Option(None, help="Override ASS Fontname for burn-in"),
    style: list[str] | None = typer.Option(None, help="Additional ASS force_style overrides (KEY=VALUE)"),
    fonts_dir: Path | None = typer.Option(None, help="Directory containing fonts for libass"),
):
    """Hard-burn subtitles into video using ffmpeg + libass."""

    styles_dict = None
    if style:
        styles_dict = {}
        for item in style:
            if "=" not in item:
                raise typer.BadParameter("Style overrides must use KEY=VALUE syntax")
            key, value = item.split("=", 1)
            styles_dict[key] = value

    result = video.burn_subs(
        video_path,
        subs_path,
        out,
        codec=codec,
        crf=crf,
        font=font,
        styles=styles_dict,
        fonts_dir=fonts_dir,
    )
    console.print(f"Burned file at {result}")


@app.command()
def batch(
    input_dir: Path,
    to: List[str] = typer.Option(..., help="Destination language codes e.g. pt-BR"),
    ext: str = typer.Option("mp4,mkv,flac", help="Comma-separated list of extensions to process"),
    workdir: Path = typer.Option(Path("workdir")),
    mode: str = typer.Option("llm", case_sensitive=False),
    provider: str = typer.Option("echo", help="Translation provider: echo|local|api"),
    block_size: int = 20,
    glossary: Optional[Path] = typer.Option(None, help="Optional glossary JSON mapping source->target"),
    model_size: str = "large-v3",
    device: Optional[str] = None,
    vad: bool = True,
    temperature: float = 0.0,
    beam_size: int = 5,
    fmt: str = typer.Option("srt", help="Subtitle format for export"),
    bilingual: Optional[str] = typer.Option(None, help="Optional secondary subtitle language"),
    mono: bool = False,
    force: bool = typer.Option(False, help="Reprocess stages even when cached"),
):
    """Batch process media files within a directory."""

    extensions = {item.strip().lower().lstrip(".") for item in ext.split(",") if item.strip()}
    media_files = sorted([p for p in Path(input_dir).rglob("*") if p.is_file() and p.suffix.lower().lstrip(".") in extensions])

    if not media_files:
        console.print("No media files found matching the provided extensions.")
        raise typer.Exit(code=1)

    glossary_data = json.loads(glossary.read_text(encoding="utf-8")) if glossary else None

    with Progress(
        TextColumn("[bold blue]{task.description}"),
        BarColumn(),
        TaskProgressColumn(),
        expand=True,
    ) as progress:
        files_task = progress.add_task("Processing files", total=len(media_files))

        for media_path in media_files:
            workdir_path = _workdir_for_media(workdir, media_path)
            workdir_path.mkdir(parents=True, exist_ok=True)
            master_path = io.master_path_from_workdir(workdir_path)
            audio_path = workdir_path / "audio.flac"
            doc: MasterDocument | None = None

            stage_task = progress.add_task(media_path.name, total=len(BATCH_STAGES))
            for stage in BATCH_STAGES:
                progress.update(stage_task, description=f"{media_path.name} • {stage}")
                if _is_stage_cached(workdir_path, stage, force):
                    progress.advance(stage_task)
                    continue

                if stage == "ingest":
                    audio_path = audio.ingest_media(media_path, workdir_path, mono=mono)
                elif stage == "transcribe":
                    doc = asr.transcribe_audio(
                        audio_path,
                        model_size=model_size,
                        vad_filter=vad,
                        temperature=temperature,
                        beam_size=beam_size,
                        device=device,
                    )
                    io.save_master(doc, master_path)
                    _write_transcripts(doc, workdir_path, prefix="transcript_ja", lang="ja")
                elif stage == "romanize":
                    doc = doc or io.load_master(master_path)
                    doc = romanizer.romanize_segments(doc)
                    io.save_master(doc, master_path)
                    _write_transcripts(doc, workdir_path, prefix="transcript_romaji", lang="ja", use_romaji=True)
                elif stage == "translate":
                    doc = doc or io.load_master(master_path)
                    doc = translation.translate_document(
                        doc,
                        target_langs=to,
                        mode=mode,
                        provider=provider,
                        block_size=block_size,
                        glossary=glossary_data,
                    )
                    io.save_master(doc, master_path)
                elif stage == "export":
                    doc = doc or io.load_master(master_path)
                    output_path = workdir_path / f"subs_{to[0]}.{fmt}"
                    subtitles.write_subtitles(doc, output_path, fmt, lang=to[0], secondary=bilingual)

                _mark_stage(workdir_path, stage)
                progress.advance(stage_task)

            progress.advance(files_task)
    console.print("Batch processing complete.")


def _workdir_for_media(base_workdir: Path, media_path: Path) -> Path:
    digest = hashlib.sha1(media_path.stem.encode("utf-8")).hexdigest()[:12]
    return Path(base_workdir) / digest


def _is_stage_cached(workdir: Path, stage: str, force: bool) -> bool:
    if force:
        return False
    return _marker_path(workdir, stage).exists()


def _mark_stage(workdir: Path, stage: str) -> None:
    _marker_path(workdir, stage).touch()


def _marker_path(workdir: Path, stage: str) -> Path:
    return Path(workdir) / f".{stage}.done"


def _write_transcripts(doc: MasterDocument, workdir: Path, prefix: str, lang: str, use_romaji: bool = False) -> None:
    workdir.mkdir(parents=True, exist_ok=True)
    text_path = workdir / f"{prefix}.txt"
    srt_path = workdir / f"{prefix}.srt"

    lines = []
    payload_segments = []
    for seg in doc.segments:
        if use_romaji and seg.romaji:
            lines.append(seg.romaji)
            seg_copy = copy.deepcopy(seg)
            seg_copy.translations = {lang: seg.romaji}
            payload_segments.append(seg_copy)
        elif lang == "ja":
            lines.append(seg.ja_raw)
            payload_segments.append(seg)
        else:
            lines.append(seg.translations.get(lang, ""))
            payload_segments.append(seg)
    text_path.write_text("\n".join(lines), encoding="utf-8")
    srt_content = subtitles.render_srt(payload_segments, lang, None)
    srt_path.write_text(srt_content, encoding="utf-8")


if __name__ == "__main__":  # pragma: no cover
    app()


# Entry point for console_scripts
main = app
