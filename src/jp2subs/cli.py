"""Typer CLI for jp2subs."""
from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import List, Optional

import typer
from rich.console import Console
from rich.progress import track

from . import __version__
from . import audio, asr, io, romanizer, subtitles, translation, video
from .models import MasterDocument

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

    doc = asr.transcribe_audio(audio_path, model_size=model_size, vad_filter=vad, temperature=temperature, beam_size=beam_size, device=device)
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
    doc = translation.translate_document(doc, target_langs=to, mode=mode, provider=provider, block_size=block_size, glossary=glossary_data)
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
def burn(video_path: Path, subs_path: Path, out: Path = typer.Option(Path("out_hard.mp4")), codec: str = "libx264", crf: int = 18):
    """Hard-burn subtitles into video using ffmpeg + libass."""
    result = video.burn_subs(video_path, subs_path, out, codec=codec, crf=crf)
    console.print(f"Burned file at {result}")


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
