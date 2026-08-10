"""Typer CLI for jp2subs."""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Callable, List, Optional, Sequence

import typer
from rich.console import Console
from rich.progress import BarColumn, Progress, TaskProgressColumn, TextColumn
from rich.prompt import Confirm, IntPrompt, Prompt
from rich.table import Table

from . import config, deps
from .paths import coerce_workdir, default_workdir_for_input, normalize_input_path, strip_quotes
from .runtime import catalog as runtime_catalog
from .runtime import store as runtime_store
from .runtime import updater
from .runtime.manager import manager as component_manager

from . import __version__
from . import audio, asr, io, romanizer, subtitles, video
from .models import MasterDocument

BATCH_STAGES: Sequence[str] = ("ingest", "transcribe", "romanize", "export")

app = typer.Typer(add_completion=False, help="jp2subs: end-to-end JP transcription and subtitling")
deps_app = typer.Typer(add_completion=False, help="Manage optional jp2subs dependencies")
components_app = typer.Typer(add_completion=False, help="Download and manage models, ffmpeg and GPU libraries")

app.add_typer(deps_app, name="deps")
app.add_typer(components_app, name="components")
console = Console()


def _version_callback(value: bool) -> None:
    if value:
        console.print(f"jp2subs {__version__}")
        raise typer.Exit()


@app.callback()
def main(
    ctx: typer.Context,
    version: bool = typer.Option(
        False, "--version", "-V", callback=_version_callback, is_eager=True, help="Show the version and exit."
    ),
):
    """jp2subs CLI entrypoint."""
    ctx.obj = {}


@deps_app.command(name="install-llama")
def deps_install_llama():
    """Download llama.cpp Windows binaries and configure jp2subs."""

    deps.install_llama(console)


@deps_app.command(name="install-model")
def deps_install_model():
    """Download a GGUF model and update configuration."""

    deps.install_model(console)


@deps_app.command()
def doctor():
    """Check local dependency health (ffmpeg, llama.cpp)."""

    code = deps.doctor(console)
    raise typer.Exit(code=code)


def _resolve_component_key(name: str) -> str:
    """Accept 'ffmpeg', 'cuda', 'large-v3' or a full 'model:large-v3' key."""

    raw = (name or "").strip().lower()
    if not raw:
        raise typer.BadParameter("Component name is required.")
    if runtime_catalog.component(raw):
        return raw

    aliases = {
        "ffmpeg": "tool:ffmpeg",
        "cuda": "accel:cuda",
        "gpu": "accel:cuda",
        "translator": runtime_catalog.default_translation_model().key,
        "translation": runtime_catalog.default_translation_model().key,
        "nllb": runtime_catalog.default_translation_model().key,
    }
    if raw in aliases and runtime_catalog.component(aliases[raw]):
        return aliases[raw]

    model = runtime_catalog.model_for_alias(raw)
    if model:
        return model.key

    known = ", ".join(item.key for item in runtime_catalog.all_components())
    raise typer.BadParameter(f"Unknown component '{name}'. Available: {known}")


def _progress_bar(label: str):
    """Rich progress bar wired to the runtime downloader's callbacks."""

    progress = Progress(
        TextColumn("[bold blue]{task.description}"),
        BarColumn(),
        TaskProgressColumn(),
        TextColumn("{task.fields[detail]}"),
        console=console,
    )
    task_id = progress.add_task(label, total=100, detail="")

    def on_progress(event) -> None:
        if event.percent < 0:
            progress.update(task_id, total=None, detail=event.detail)
        else:
            progress.update(task_id, total=100, completed=event.percent, detail=event.detail)

    return progress, on_progress


def _install_with_progress(key: str) -> None:
    """Install one catalog component while drawing a progress bar."""

    item = runtime_catalog.component(key)
    label = item.name if item else key
    progress, on_progress = _progress_bar(label)
    with progress:
        component_manager.install(key, on_progress=on_progress)
    console.print(f"[green]Installed[/green] {label}")


def _install_repo_with_progress(repo_id: str) -> None:
    """Install any CTranslate2 Whisper repository straight from Hugging Face."""

    from .runtime import search as model_search

    found = model_search.inspect_repo(repo_id)
    if not found:
        raise typer.BadParameter(f"Could not find '{repo_id}' on Hugging Face.")
    if not found.is_loadable:
        raise typer.BadParameter(
            f"'{found.repo_id}' is not in CTranslate2 format (no model.bin plus config.json). "
            "Look for a build with 'faster-whisper' or 'ct2' in the name."
        )

    console.print(f"Installing [bold]{found.repo_id}[/bold] ({runtime_store.human_size(found.size)})")
    progress, on_progress = _progress_bar(found.repo_id)
    with progress:
        component_manager.install_custom_model(
            found.repo_id, approx_size=found.size, name=found.repo_id, on_progress=on_progress
        )
    console.print(f"[green]Installed[/green] {found.repo_id}")


@components_app.command("search")
def components_search(
    query: str = typer.Argument("faster-whisper", help="Words to search for, or an owner/model id"),
    limit: int = typer.Option(15, help="How many results to show"),
):
    """Search Hugging Face for Whisper models this app can load."""

    from .runtime import search as model_search

    console.print(f"Searching Hugging Face for [bold]{query}[/bold]...")
    try:
        results = model_search.search_models(query, limit=limit)
    except Exception as exc:  # noqa: BLE001
        console.print(f"[red]Search failed:[/red] {exc}")
        raise typer.Exit(code=1)

    if not results:
        console.print("No CTranslate2 models matched. Try 'faster-whisper' or 'ct2' in the query.")
        raise typer.Exit(code=1)

    table = Table(title=f"{len(results)} usable model(s)")
    table.add_column("Repository")
    table.add_column("Size", justify="right")
    table.add_column("Downloads", justify="right")
    table.add_column("Installed")

    for item in results:
        installed = component_manager.is_installed(f"model:hf:{item.repo_id}")
        table.add_row(
            item.repo_id,
            runtime_store.human_size(item.size),
            f"{item.downloads:,}",
            "[green]yes[/green]" if installed else "",
        )

    console.print(table)
    console.print("Install one with: [bold]jp2subs components install <repository>[/bold]")


@components_app.command("list")
def components_list():
    """Show every downloadable component and whether it is installed."""

    table = Table(title=f"Components in {runtime_store.data_dir()}")
    table.add_column("Key")
    table.add_column("Name")
    table.add_column("Status")
    table.add_column("Size")
    table.add_column("Notes")

    for status in component_manager.statuses():
        item = status.component
        if status.installed:
            state = "[green]installed[/green]"
            size = runtime_store.human_size(status.size)
        else:
            state = "[dim]not installed[/dim]"
            size = f"~{runtime_store.human_size(item.approx_size)}"
        tags = []
        if item.required:
            tags.append("required")
        if item.recommended:
            tags.append("recommended")
        table.add_row(item.key, item.name, state, size, ", ".join(tags))

    console.print(table)
    total = component_manager.total_size()
    console.print(f"Using {runtime_store.human_size(total)} on disk." if total else "Nothing downloaded yet.")


@components_app.command("install")
def components_install(
    name: str = typer.Argument(
        ..., help="ffmpeg, cuda, translator, a model name, or a Hugging Face owner/model id"
    )
):
    """Download and install a component."""

    if "/" in name:
        _install_repo_with_progress(name)
        return
    _install_with_progress(_resolve_component_key(name))


@components_app.command("remove")
def components_remove(name: str = typer.Argument(..., help="ffmpeg, cuda, a model name, or a full key")):
    """Delete an installed component from disk."""

    key = f"model:hf:{name}" if "/" in name else _resolve_component_key(name)
    component_manager.uninstall(key)
    console.print(f"[green]Removed[/green] {key}")


@components_app.command("path")
def components_path():
    """Print the folder where downloaded components live."""

    console.print(str(runtime_store.data_dir()))


@app.command(name="setup")
def setup_cmd(
    model: str = typer.Option(
        "", "--model", help="Model to install (default: the recommended one). Use 'none' to skip."
    ),
    gpu: bool = typer.Option(False, "--gpu", help="Also install the NVIDIA acceleration libraries."),
):
    """Install everything jp2subs needs to run: ffmpeg and a speech model."""

    if not component_manager.is_installed("tool:ffmpeg") and not config.detect_ffmpeg(None):
        _install_with_progress("tool:ffmpeg")
    else:
        console.print("[green]ffmpeg is already available.[/green]")

    if model.strip().lower() == "none":
        console.print("Skipping the model download.")
    elif component_manager.installed_models() and not model:
        installed = ", ".join(item.name for item in component_manager.installed_models())
        console.print(f"[green]Model already installed:[/green] {installed}")
    else:
        key = _resolve_component_key(model) if model else runtime_catalog.recommended_model_key()
        if component_manager.is_installed(key):
            console.print(f"[green]{key} is already installed.[/green]")
        else:
            _install_with_progress(key)

    if gpu:
        cuda = runtime_catalog.cuda_component()
        if not cuda:
            console.print("[yellow]GPU acceleration is only offered on 64-bit Windows.[/yellow]")
        elif component_manager.is_installed(cuda.key):
            console.print("[green]GPU libraries are already installed.[/green]")
        else:
            _install_with_progress(cuda.key)

    console.print("\n[bold green]Setup complete.[/bold green] Run [bold]jp2subs ui[/bold] to open the app.")


@app.command(name="update")
def update_cmd(
    install: bool = typer.Option(False, "--install", help="Download the new release and start the installer."),
    prerelease: bool = typer.Option(False, "--prerelease", help="Consider pre-releases too."),
):
    """Check whether a newer release of jp2subs is available."""

    try:
        release = updater.check_for_updates(include_prerelease=prerelease)
    except Exception as exc:  # noqa: BLE001
        console.print(f"[red]Could not reach GitHub:[/red] {exc}")
        raise typer.Exit(code=1)

    if not release:
        console.print(f"[green]jp2subs {__version__} is the latest version.[/green]")
        return

    console.print(f"[bold]Version {release.version} is available[/bold] (you have {__version__}).")
    console.print(release.html_url)
    if release.notes:
        console.print(f"\n{release.notes.strip()[:1500]}\n")

    if not install:
        console.print("Run [bold]jp2subs update --install[/bold] to download and install it.")
        return

    if not release.has_installer:
        console.print("[yellow]This release has no installer for your platform. Download it from the page above.[/yellow]")
        raise typer.Exit(code=1)

    with Progress(
        TextColumn("[bold blue]{task.description}"),
        BarColumn(),
        TaskProgressColumn(),
        TextColumn("{task.fields[detail]}"),
        console=console,
    ) as progress:
        task_id = progress.add_task(release.asset_name, total=100, detail="")

        def on_progress(event) -> None:
            if event.percent < 0:
                progress.update(task_id, total=None, detail=event.detail)
            else:
                progress.update(task_id, total=100, completed=event.percent, detail=event.detail)

        path = updater.download_update(release, on_progress=on_progress)

    console.print(f"Downloaded to [bold]{path}[/bold]")
    updater.launch_installer(path)
    console.print("The installer has been started. Close jp2subs so it can finish.")


@app.command(name="install-llama")
def install_llama_alias():
    """Shortcut for `jp2subs deps install-llama`."""

    deps.install_llama(console)


@app.command(name="install-model")
def install_model_alias():
    """Shortcut for `jp2subs deps install-model`."""

    deps.install_model(console)


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
    device: str = typer.Option("auto", help="ASR device: auto|cuda|cpu"),
    vad: bool = True,
    temperature: float = 0.0,
    beam_size: int = 5,
):
    """Run ASR and produce master.json."""

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
    console.print(f"Master JSON saved to [bold]{master_path}[/bold]")


@app.command()
def romanize(master: Path, workdir: Path = typer.Option(Path("workdir"))):
    """Generate romaji from Japanese transcription."""
    doc = io.load_master(master)
    doc = romanizer.romanize_segments(doc)
    io.save_master(doc, master)
    output_path = _write_romaji_subtitles(doc, workdir, fmt="srt")
    console.print(f"Romaji subtitle written to [bold]{output_path}[/bold].")


@app.command()
def translate(
    master: Path,
    to: str = typer.Option("", "--to", help="Comma-separated target languages, e.g. en,pt-BR"),
    engine: str = typer.Option("offline", help="offline, deepl or openai"),
    fmt: str = typer.Option("srt", help="Subtitle format to export: srt|vtt|ass"),
    workdir: Optional[Path] = typer.Option(None, help="Where to write subtitles (defaults to the master's folder)"),
    bilingual: bool = typer.Option(False, help="Also write a track with Japanese underneath"),
    list_languages: bool = typer.Option(False, "--list-languages", help="List the language codes and exit"),
):
    """Translate an existing master.json and export subtitles."""

    from .translation import LANGUAGES, resolve_many, translate_document

    if list_languages:
        table = Table(title="Target languages")
        table.add_column("Code")
        table.add_column("Language")
        table.add_column("DeepL")
        for language in LANGUAGES:
            table.add_row(language.code, language.name, language.deepl or "—")
        console.print(table)
        return

    targets = resolve_many([item.strip() for item in to.split(",") if item.strip()])
    if not targets:
        raise typer.BadParameter("No recognised language codes. Run with --list-languages to see them.")

    doc = io.load_master(master)
    out_dir = Path(workdir) if workdir else Path(master).parent
    out_dir.mkdir(parents=True, exist_ok=True)

    console.print(
        f"Translating {len(doc.segments)} segment(s) into "
        f"{', '.join(language.name for language in targets)} using [bold]{engine}[/bold]"
    )

    progress, on_progress = _progress_bar("Translating")
    with progress:
        doc = translate_document(doc, targets, engine=engine, on_progress=on_progress)

    io.save_master(doc, master)

    for language in targets:
        output_path = out_dir / f"subs_{language.code}.{fmt}"
        subtitles.write_subtitles(doc, output_path, fmt, lang=language.code, secondary=None)
        console.print(f"Wrote [bold]{output_path}[/bold]")
        if bilingual:
            dual_path = out_dir / f"subs_{language.code}_bilingual.{fmt}"
            subtitles.write_subtitles(doc, dual_path, fmt, lang="ja", secondary=language.code)
            console.print(f"Wrote [bold]{dual_path}[/bold]")


@app.command()
def export(
    master: Path,
    fmt: str = typer.Option("srt", help="Subtitle format: srt|vtt|ass"),
    lang: str = typer.Option("ja", help="Primary language code"),
    out: Optional[Path] = typer.Option(None, help="Output path; defaults to workdir/subs_<lang>.<fmt>"),
    workdir: Path = typer.Option(Path("workdir")),
):
    """Export subtitles for a given language and format."""

    doc = io.load_master(master)
    output_path = out or (Path(workdir) / f"subs_{lang}.{fmt}")
    subtitles.write_subtitles(doc, output_path, fmt, lang=lang, secondary=None)
    console.print(f"Subtitle written to [bold]{output_path}[/bold]")


@app.command()
def softcode(
    video_path: Path,
    subtitle: Path,
    out_dir: Path | None = typer.Option(None, help="Output directory"),
    container: str = typer.Option("mkv", case_sensitive=False, help="Output container mkv|mp4"),
    same_name: bool = typer.Option(False, help="Name output after the video"),
    suffix: str | None = typer.Option(None, help="Optional suffix before extension"),
    lang: str | None = typer.Option("en", help="Subtitle language code"),
    out: Path | None = typer.Option(None, help="Override output path"),
    verbose: bool = typer.Option(False, help="Show ffmpeg command"),
):
    """Soft-mux subtitles into a container."""

    container = container.lower()
    out_path = video.build_out_path(
        video_path, subtitle, out_dir, same_name, suffix, container, mode="softcode", out=out
    )
    console.print("[bold]Mode:[/bold] softcode")
    console.print(f"Video: {video_path}")
    console.print(f"Subtitle: {subtitle}")
    console.print(f"Output: {out_path}")
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
    console.print("[bold]Mode:[/bold] hardcode")
    console.print(f"Video: {video_path}")
    console.print(f"Subtitle: {subtitle}")
    console.print(f"Output: {out_path}")
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
    console.print("[bold]Mode:[/bold] sidecar")
    console.print(f"Video: {video_path}")
    console.print(f"Subtitle: {subtitle}")
    console.print(f"Output: {out_path}")
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


def _prompt_choice(label: str, options: dict[str, str], default: str) -> str:
    rendered = " ".join([f"[{key}] {value}" for key, value in options.items()])
    prompt_text = f"{label} {rendered} (default {default})"
    while True:
        raw = Prompt.ask(prompt_text, default=default)
        answer = strip_quotes(raw).lower()
        if answer == "":
            answer = default
        if answer in options:
            return answer
        console.print("[red]Invalid choice.[/red]")


def _prompt_path(label: str, allow_file: bool = True, allow_dir: bool = False) -> Path:
    value = Prompt.ask(label).strip()
    if value == "":
        picked = _open_file_picker(allow_dir=allow_dir)
        value = picked or value
    normalized = normalize_input_path(value)
    if allow_dir and normalized.suffix and not allow_file:
        normalized = normalized.parent
    return normalized


def _open_file_picker(allow_dir: bool = False) -> str:
    try:
        import tkinter.filedialog as fd
        import tkinter as tk

        root = tk.Tk()
        root.withdraw()
        if allow_dir:
            return fd.askdirectory(title="Choose a folder")
        return fd.askopenfilename(title="Choose a file")
    except Exception:
        return ""


def _doctor_ffmpeg() -> None:
    ffmpeg_path = config.detect_ffmpeg()
    if not ffmpeg_path:
        raise typer.BadParameter("ffmpeg not found on PATH. Install it or configure it in Settings.")


def _open_in_file_manager(path: Path) -> None:
    target = Path(path).resolve()
    if not target.exists():
        console.print(f"[red]Workdir not found:[/red] {target}")
        return
    try:
        if sys.platform.startswith("win"):
            os.startfile(target)  # type: ignore[attr-defined]
        elif sys.platform.startswith("darwin"):
            subprocess.run(["open", str(target)], check=False)
        else:
            subprocess.run(["xdg-open", str(target)], check=False)
    except Exception as exc:  # noqa: BLE001
        console.print(f"[red]Could not open workdir:[/red] {exc}")


def _summarize_config(defaults: config.AppConfig | None = None) -> config.AppConfig:
    cfg = defaults or config.load_config()
    detected_ffmpeg = config.detect_ffmpeg(cfg.ffmpeg_path)
    if detected_ffmpeg:
        cfg.ffmpeg_path = detected_ffmpeg
    return cfg


def _default_workdir(input_path: Path) -> Path:
    return Path("workdir") / input_path.stem


def _wizard_impl(open_workdir: bool = False):
    console.print("[bold]jp2subs Wizard[/bold] — interactive guided run\n")
    cfg = _summarize_config()
    input_path = _prompt_path("Input media/audio path (Enter opens file picker)")
    if not input_path.exists():
        console.print(f"[red]Input path not found:[/red] {input_path}")
        raise typer.Exit(code=1)

    workdir_default = default_workdir_for_input(input_path)
    workdir_input = Prompt.ask("Work directory", default=str(workdir_default))
    workdir = coerce_workdir(workdir_input)

    mono_choice = _prompt_choice("Mono audio?", {"1": "mono", "2": "stereo"}, "2")
    mono = mono_choice == "1"
    model_size = Prompt.ask("Transcription model size", default=cfg.defaults.model_size)
    beam_size = IntPrompt.ask("Beam size", default=cfg.defaults.beam_size)
    vad_choice = _prompt_choice("VAD filter?", {"1": "on", "2": "off"}, "1" if cfg.defaults.vad else "2")
    vad_filter = vad_choice == "1"
    device_choice = _prompt_choice("Device: [1] auto [2] cuda [3] cpu", {"1": "auto", "2": "cuda", "3": "cpu"}, "1")
    device = {"1": "auto", "2": "cuda", "3": "cpu"}[device_choice]

    romaji_choice = _prompt_choice("Generate romaji?", {"y": "yes", "n": "no"}, "n")
    generate_romaji = romaji_choice == "y"
    console.print(
        "[dim]Tip: translate the result afterwards with "
        "'jp2subs translate <workdir>/master.json --to en,pt-BR'.[/dim]"
    )
    fmt_choice = _prompt_choice("Subtitle format", {"1": "srt", "2": "vtt", "3": "ass"}, "1")
    fmt = {"1": "srt", "2": "vtt", "3": "ass"}[fmt_choice]
    output_choice = _prompt_choice(
        "Output type", {"1": "subtitles", "2": "mux-soft", "3": "burn"}, "1"
    )
    output_mode = {"1": "subtitles", "2": "mux-soft", "3": "burn"}[output_choice]

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
            device=device,
        )
        master_path = io.master_path_from_workdir(workdir)
        io.save_master(doc, master_path)
        generated_paths.append(master_path)
        return doc

    def stage_romanize(doc: MasterDocument) -> MasterDocument:
        doc = romanizer.romanize_segments(doc)
        master_path = io.master_path_from_workdir(workdir)
        io.save_master(doc, master_path)
        generated_paths.append(_write_romaji_subtitles(doc, workdir, fmt=fmt))
        return doc

    def stage_export(doc: MasterDocument) -> list[Path]:
        exports: list[Path] = []
        output_path = workdir / f"subs_ja.{fmt}"
        subtitles.write_subtitles(doc, output_path, fmt, lang="ja", secondary=None)
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

    if open_workdir:
        _open_in_file_manager(workdir)


def _finalize_wizard():
    console.print("[bold]Finalize Wizard[/bold] — mux/burn/sidecar\n")
    video_path = _prompt_path("Input video (Enter opens file picker)")
    if not video_path.exists():
        console.print(f"[red]Video not found:[/red] {video_path}")
        raise typer.Exit(code=1)

    subtitle_path = _prompt_path("Subtitle (SRT/VTT/ASS)")
    if not subtitle_path.exists():
        console.print(f"[red]Subtitle not found:[/red] {subtitle_path}")
        raise typer.Exit(code=1)

    mode_choice = _prompt_choice("Mode", {"1": "sidecar", "2": "softcode", "3": "hardcode"}, "1")
    target_dir_input = Prompt.ask("Output folder (Enter = same as video)", default="")
    target_dir = Path(target_dir_input) if target_dir_input else video_path.parent

    suffix = None
    codec = "libx264"
    crf = 18
    if mode_choice == "3":
        crf = IntPrompt.ask("CRF", default=18)
        codec = Prompt.ask("Codec", default="libx264")

    if mode_choice == "1":
        out_path = video.build_out_path(video_path, subtitle_path, target_dir, True, suffix, None, mode="sidecar")
        result = video.copy_sidecar(video_path, subtitle_path, out_path)
    elif mode_choice == "2":
        out_path = video.build_out_path(video_path, subtitle_path, target_dir, True, suffix, "mkv", mode="softcode")
        result = video.run_ffmpeg_mux_soft(video_path, subtitle_path, out_path, container="mkv", lang="ja")
    else:
        out_path = video.build_out_path(video_path, subtitle_path, target_dir, True, suffix, "mp4", mode="hardcode")
        result = video.run_ffmpeg_burn(video_path, subtitle_path, out_path, codec=codec, crf=crf, preset="slow")

    console.print(f"[green]Done:[/green] {result}")


@app.command(name="wizard")
def wizard_cmd(
    open_workdir: bool = typer.Option(
        False, "--open-workdir", help="Open the workdir folder in the file explorer after completion"
    )
):
    """Run the interactive jp2subs wizard."""

    _wizard_impl(open_workdir=open_workdir)


@app.command(name="menu")
def menu_cmd(
    open_workdir: bool = typer.Option(
        False, "--open-workdir", help="Open the workdir folder in the file explorer after completion"
    )
):
    """Alias for the interactive wizard."""

    _wizard_impl(open_workdir=open_workdir)


@app.command(name="w")
def wizard_shortcut(
    open_workdir: bool = typer.Option(
        False, "--open-workdir", help="Open the workdir folder in the file explorer after completion"
    )
):
    """Shortcut for wizard."""

    _wizard_impl(open_workdir=open_workdir)


@app.command(name="finalize")
def finalize_cmd():
    """Finalize wizard for mux/burn/sidecar."""

    _finalize_wizard()


@app.command(name="f")
def finalize_shortcut():
    """Shortcut for finalize wizard."""

    _finalize_wizard()


@app.command(name="ui")
def ui_cmd():
    """Launch the desktop GUI."""

    try:
        from .gui.main import launch
    except Exception as exc:  # pragma: no cover - depends on environment
        raise typer.BadParameter(f"Falha ao abrir UI: {exc}") from exc

    launch()


@app.command()
def batch(
    input_dir: Path,
    ext: str = typer.Option("mp4,mkv,flac", help="Comma-separated list of extensions to process"),
    workdir: Path = typer.Option(Path("workdir")),
    model_size: str = "large-v3",
    device: Optional[str] = None,
    vad: bool = True,
    temperature: float = 0.0,
    beam_size: int = 5,
    fmt: str = typer.Option("srt", help="Subtitle format for export"),
    mono: bool = False,
    force: bool = typer.Option(False, help="Reprocess stages even when cached"),
):
    """Batch process media files within a directory."""

    extensions = {item.strip().lower().lstrip(".") for item in ext.split(",") if item.strip()}
    media_files = sorted([p for p in Path(input_dir).rglob("*") if p.is_file() and p.suffix.lower().lstrip(".") in extensions])

    if not media_files:
        console.print("No media files found matching the provided extensions.")
        raise typer.Exit(code=1)

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
                elif stage == "romanize":
                    doc = doc or io.load_master(master_path)
                    doc = romanizer.romanize_segments(doc)
                    io.save_master(doc, master_path)
                    _write_romaji_subtitles(doc, workdir_path, fmt=fmt)
                elif stage == "export":
                    doc = doc or io.load_master(master_path)
                    output_path = workdir_path / f"subs_ja.{fmt}"
                    subtitles.write_subtitles(doc, output_path, fmt, lang="ja", secondary=None)

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


def _write_romaji_subtitles(doc: MasterDocument, workdir: Path, fmt: str) -> Path:
    workdir.mkdir(parents=True, exist_ok=True)
    output_path = workdir / f"subs_romaji.{fmt}"
    subtitles.write_romaji_subtitles(doc, output_path, fmt)
    return output_path


if __name__ == "__main__":  # pragma: no cover
    app()


# Entry point for console_scripts
main = app
