"""Typer CLI for jp2subs."""
from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
from typing import Callable, List, Optional, Sequence

import typer
from rich.console import Console
from rich.progress import BarColumn, Progress, TaskProgressColumn, TextColumn
from rich.prompt import Confirm, IntPrompt, Prompt

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


@app.command()
def softcode(
    video_path: Path,
    subtitle: Path,
    out_dir: Path | None = typer.Option(None, help="Output directory"),
    container: str = typer.Option("mkv", case_sensitive=False, help="Output container mkv|mp4"),
    same_name: bool = typer.Option(False, help="Name output after the video"),
    suffix: str | None = typer.Option(None, help="Optional suffix before extension"),
    lang: str | None = typer.Option("pt-BR", help="Subtitle language code"),
    out: Path | None = typer.Option(None, help="Override output path"),
    verbose: bool = typer.Option(False, help="Show ffmpeg command"),
):
    """Soft-mux subtitles into a container."""

    container = container.lower()
    out_path = video.build_out_path(
        video_path, subtitle, out_dir, same_name, suffix, container, mode="softcode", out=out
    )
    console.print("[bold]Modo:[/bold] softcode")
    console.print(f"Vídeo: {video_path}")
    console.print(f"Legenda: {subtitle}")
    console.print(f"Saída: {out_path}")
    result = video.run_ffmpeg_mux_soft(
        video_path, subtitle, out_path, container=container, lang=lang, verbose=verbose
    )
    console.print(f"Muxed file at [bold]{result}[/bold]")


@app.command()
def hardcode(
    video_path: Path,
    subtitle: Path,
    out_dir: Path | None = typer.Option(None, help="Output directory"),
    same_name: bool = typer.Option(False, help="Name output after the video"),
    suffix: str | None = typer.Option(".hard", help="Suffix before extension"),
    codec: str = typer.Option("libx264", help="Video codec for re-encode"),
    crf: int = typer.Option(18, help="Constant Rate Factor"),
    preset: str = typer.Option("slow", help="FFmpeg preset"),
    out: Path | None = typer.Option(None, help="Override output path"),
    verbose: bool = typer.Option(False, help="Show ffmpeg command"),
):
    """Hard-burn subtitles into the video."""

    out_path = video.build_out_path(
        video_path, subtitle, out_dir, same_name, suffix, container="mp4", mode="hardcode", out=out
    )
    console.print("[bold]Modo:[/bold] hardcode")
    console.print(f"Vídeo: {video_path}")
    console.print(f"Legenda: {subtitle}")
    console.print(f"Saída: {out_path}")
    result = video.run_ffmpeg_burn(
        video_path,
        subtitle,
        out_path,
        codec=codec,
        crf=crf,
        preset=preset,
        verbose=verbose,
    )
    console.print(f"Burned file at [bold]{result}[/bold]")


@app.command()
def sidecar(
    video_path: Path,
    subtitle: Path,
    out_dir: Path | None = typer.Option(None, help="Output directory"),
    same_name: bool = typer.Option(False, help="Rename subtitle to video stem"),
    out: Path | None = typer.Option(None, help="Override output path"),
):
    """Copy subtitles as a sidecar file alongside the video."""

    out_path = video.build_out_path(
        video_path, subtitle, out_dir, same_name, suffix=None, container=None, mode="sidecar", out=out
    )
    console.print("[bold]Modo:[/bold] sidecar")
    console.print(f"Vídeo: {video_path}")
    console.print(f"Legenda: {subtitle}")
    console.print(f"Saída: {out_path}")
    result = video.copy_sidecar(video_path, subtitle, out_path)
    console.print(f"Sidecar ready at [bold]{result}[/bold]")


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


def _parse_languages(raw_value: str) -> list[str]:
    langs = [lang.strip() for lang in raw_value.split(",") if lang.strip()]
    if not langs:
        raise typer.BadParameter("At least one target language is required")
    return langs


def _default_workdir(input_path: Path) -> Path:
    return Path("workdir") / input_path.stem


def _wizard_impl():
    console.print("[bold]jp2subs Wizard[/bold] — interactive guided run\n")
    input_raw = Prompt.ask("Input media/audio path")
    input_path = Path(input_raw).expanduser()
    if not input_path.exists():
        console.print(f"[red]Input path not found:[/red] {input_path}")
        raise typer.Exit(code=1)

    workdir_default = _default_workdir(input_path)
    workdir = Path(Prompt.ask("Work directory", default=str(workdir_default))).expanduser()

    mono = Confirm.ask("Extract mono audio?", default=False)
    model_size = Prompt.ask("Transcription model size", default="large-v3")
    beam_size = IntPrompt.ask("Beam size", default=5)
    vad_filter = Confirm.ask("Enable VAD filtering?", default=True)

    generate_romaji = Confirm.ask("Generate romaji transcript?", default=False)

    langs_raw = Prompt.ask("Translation target languages (comma-separated, e.g., en, pt-BR)")
    try:
        target_langs = _parse_languages(langs_raw)
    except typer.BadParameter as exc:  # pragma: no cover - handled in tests via invoke
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=1)

    translation_mode = Prompt.ask("Translation mode", choices=["llm", "draft+postedit"], default="llm")
    provider = Prompt.ask("Translation provider", choices=["local", "api"], default="local")
    fmt = Prompt.ask("Subtitle format", choices=["srt", "vtt", "ass"], default="srt")
    bilingual = Prompt.ask("Bilingual secondary language (optional, e.g., ja)", default="") or None
    output_mode = Prompt.ask("Output type", choices=["subtitles", "mux-soft", "burn"], default="subtitles")

    steps: list[tuple[str, Callable[..., object]]] = []
    generated_paths: list[Path] = []

    def stage_ingest() -> Path:
        return audio.ingest_media(input_path, workdir, mono=mono)

    def stage_transcribe(audio_path: Path) -> MasterDocument:
        doc = asr.transcribe_audio(
            audio_path,
            model_size=model_size,
            vad_filter=vad_filter,
            temperature=0.0,
            beam_size=beam_size,
            device=None,
        )
        master_path = io.master_path_from_workdir(workdir)
        io.save_master(doc, master_path)
        _write_transcripts(doc, workdir, prefix="transcript_ja", lang="ja")
        generated_paths.extend(
            [master_path, workdir / "transcript_ja.txt", workdir / "transcript_ja.srt"]
        )
        return doc

    def stage_romanize(doc: MasterDocument) -> MasterDocument:
        doc = romanizer.romanize_segments(doc)
        master_path = io.master_path_from_workdir(workdir)
        io.save_master(doc, master_path)
        _write_transcripts(doc, workdir, prefix="transcript_romaji", lang="ja", use_romaji=True)
        generated_paths.extend([workdir / "transcript_romaji.txt", workdir / "transcript_romaji.srt"])
        return doc

    def stage_translate(doc: MasterDocument) -> MasterDocument:
        doc = translation.translate_document(
            doc, target_langs=target_langs, mode=translation_mode, provider=provider, block_size=20, glossary=None
        )
        master_path = io.master_path_from_workdir(workdir)
        io.save_master(doc, master_path)
        generated_paths.append(master_path)
        return doc

    def stage_export(doc: MasterDocument) -> list[Path]:
        exports: list[Path] = []
        for lang in target_langs:
            output_path = workdir / f"subs_{lang}.{fmt}"
            subtitles.write_subtitles(doc, output_path, fmt, lang=lang, secondary=bilingual)
            exports.append(output_path)
        generated_paths.extend(exports)
        return exports

    def stage_mux(subs_path: Path) -> Path:
        if not audio.is_video(input_path):
            raise typer.BadParameter("Muxing requires a video input")
        out_path = workdir / f"{input_path.stem}_soft.mkv"
        return video.mux_soft(input_path, subs_path, out_path)

    def stage_burn(subs_path: Path) -> Path:
        if not audio.is_video(input_path):
            raise typer.BadParameter("Burn-in requires a video input")
        out_path = workdir / f"{input_path.stem}_hard.mp4"
        return video.burn_subs(input_path, subs_path, out_path)

    steps.append(("Ingest", stage_ingest))
    steps.append(("Transcribe", stage_transcribe))
    if generate_romaji:
        steps.append(("Romanize", stage_romanize))
    steps.append(("Translate", stage_translate))
    steps.append(("Export", stage_export))

    console.print("\nRunning pipeline...\n")
    audio_path: Path | None = None
    doc: MasterDocument | None = None
    export_paths: list[Path] = []
    with Progress(TextColumn("[bold blue]{task.description}"), BarColumn(), TaskProgressColumn(), expand=True) as progress:
        task = progress.add_task("Processing", total=len(steps) + (1 if output_mode != "subtitles" else 0))

        for label, handler in steps:
            progress.update(task, description=label)
            if label == "Ingest":
                audio_path = handler()
            elif label == "Transcribe":
                doc = handler(audio_path)  # type: ignore[arg-type]
            elif label in {"Romanize", "Translate"}:
                doc = handler(doc)  # type: ignore[arg-type]
            elif label == "Export":
                export_paths = handler(doc)  # type: ignore[arg-type]
            progress.advance(task)

        if output_mode == "mux-soft":
            progress.update(task, description="Mux (soft)")
            muxed = stage_mux(export_paths[0])
            generated_paths.append(muxed)
            progress.advance(task)
        elif output_mode == "burn":
            progress.update(task, description="Burn (hard)")
            burned = stage_burn(export_paths[0])
            generated_paths.append(burned)
            progress.advance(task)

    console.print("\n[bold green]Wizard complete![/bold green]\nGenerated files:")
    for path in generated_paths:
        console.print(f"- {path}")


@app.command(name="wizard")
def wizard_cmd():
    """Run the interactive jp2subs wizard."""

    _wizard_impl()


@app.command(name="menu")
def menu_cmd():
    """Alias for the interactive wizard."""

    _wizard_impl()


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
