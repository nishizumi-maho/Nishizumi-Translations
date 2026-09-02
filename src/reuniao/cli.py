"""Command line for the meeting transcriber.

Everything the desktop app does is available here too, which is what makes it
scriptable: transcribe a folder of recordings overnight, install the
components on a fresh machine, or check what is already on disk.
"""
from __future__ import annotations

from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from . import branding, components, diarize
from .config import Settings, load_settings, parse_speaker_names, save_settings
from .pipeline import Cancelled, Job, Runner
from .progress import ProgressEvent, format_duration_pt

app = typer.Typer(
    add_completion=False,
    help=f"{branding.APP_NAME} — {branding.APP_TAGLINE}",
    no_args_is_help=True,
)
console = Console()


@app.command("transcrever")
def transcribe_command(
    arquivo: list[Path] = typer.Argument(..., help="Áudio ou vídeo da reunião."),
    saida: Path = typer.Option(None, "--saida", "-s", help="Pasta onde salvar. Padrão: ao lado do arquivo."),
    modelo: str = typer.Option("", "--modelo", "-m", help="Modelo Whisper. Padrão: o melhor instalado."),
    dispositivo: str = typer.Option("auto", "--dispositivo", "-d", help="auto, cuda ou cpu."),
    interlocutores: bool = typer.Option(
        True, "--interlocutores/--sem-interlocutores", help="Identificar quem falou cada trecho."
    ),
    nomes: str = typer.Option("", "--nomes", "-n", help='Nomes na ordem de fala: "Ana,João,Carla".'),
    separacao: float = typer.Option(
        0.0,
        "--separacao",
        help="Separação das vozes, de 0.1 a 1.5. Menor separa mais, maior junta mais. 0 = usar o salvo.",
    ),
    formato: str = typer.Option("blocos", "--formato", "-f", help="Layout do .txt: blocos ou linhas."),
    srt: bool = typer.Option(False, "--srt", help="Também salvar legenda .srt."),
    vtt: bool = typer.Option(False, "--vtt", help="Também salvar legenda .vtt."),
    json_out: bool = typer.Option(False, "--json", help="Também salvar os dados em .json."),
    beam: int = typer.Option(0, "--beam", help="Beam size do Whisper. 0 = usar o salvo."),
    sem_vad: bool = typer.Option(False, "--sem-vad", help="Não pular os silêncios antes de transcrever."),
    threads: int = typer.Option(0, "--threads", help="Núcleos de CPU. 0 = automático."),
    prompt: str = typer.Option("", "--prompt", help="Texto de contexto passado ao Whisper."),
) -> None:
    """Transcreve uma reunião e salva o texto."""

    settings = load_settings()
    settings.model = modelo or settings.model
    settings.device = dispositivo
    settings.identify_speakers = interlocutores
    if separacao:
        settings.clustering_threshold = separacao
    settings.layout = formato
    settings.also_srt = srt
    settings.also_vtt = vtt
    settings.also_json = json_out
    settings.vad = not sem_vad
    if nomes:
        settings.speaker_names = parse_speaker_names(nomes)
    if beam:
        settings.beam_size = beam
    if threads:
        settings.threads = threads
    if prompt:
        settings.initial_prompt = prompt
    settings.normalize()

    _warn_about_setup(settings)

    failures = 0
    for item in arquivo:
        console.rule(f"[bold]{item.name}")
        runner = Runner(on_progress=_print_progress, on_log=lambda line: console.log(line))
        try:
            result = runner.run(Job(source=item, settings=settings, output_dir=saida))
        except Cancelled:
            console.print("[yellow]Cancelado.")
            raise typer.Exit(code=130)
        except Exception as exc:  # noqa: BLE001 - the CLI reports, it does not crash
            failures += 1
            console.print(f"[red]Falhou:[/red] {exc}")
            continue

        transcript = result.transcript
        console.print()
        console.print(f"[green]Pronto:[/green] {result.text_file}")
        console.print(
            f"  {len(transcript.utterances)} falas · "
            f"{format_duration_pt(transcript.duration)} · "
            + (
                f"{transcript.speaker_count} interlocutores"
                if transcript.diarized
                else "sem identificação de interlocutores"
            )
        )
        for note in transcript.notes:
            console.print(f"  [yellow]•[/yellow] {note}")

    if failures:
        raise typer.Exit(code=1)


@app.command("componentes")
def components_command() -> None:
    """Mostra o que já está instalado e o que ainda falta baixar."""

    from jp2subs.runtime.manager import manager

    for title, hint, items in components.page_sections():
        table = Table(title=f"{title} — {hint}", title_justify="left", header_style="bold")
        table.add_column("Chave")
        table.add_column("Componente")
        table.add_column("Tamanho", justify="right")
        table.add_column("Situação")
        for item in items:
            installed = manager.is_installed(item.key)
            table.add_row(
                item.key,
                item.name,
                components.human_size(item.approx_size),
                "[green]instalado" if installed else "não instalado",
            )
        console.print(table)
        console.print()

    console.print(f"Total em disco: {components.human_size(components.installed_size())}")
    missing = components.missing_essentials()
    if missing:
        console.print(f"[yellow]Falta instalar:[/yellow] {', '.join(item.name for item in missing)}")
        console.print("Execute: [bold]reuniao preparar[/bold]")


@app.command("instalar")
def install_command(
    chave: list[str] = typer.Argument(..., help="Chaves mostradas por 'reuniao componentes'."),
) -> None:
    """Baixa e instala componentes pelo nome da chave."""

    for key in chave:
        _install(key)


@app.command("preparar")
def prepare_command(
    modelo: str = typer.Option("", "--modelo", "-m", help="Modelo a instalar. Padrão: o recomendado."),
    sem_interlocutores: bool = typer.Option(
        False, "--sem-interlocutores", help="Não instalar o pacote de identificação de vozes."
    ),
) -> None:
    """Instala o necessário para transcrever: FFmpeg, um modelo e as vozes."""

    from jp2subs.runtime.manager import manager

    wanted = [components.ffmpeg().key]
    if modelo:
        match = next((item for item in components.models() if modelo in {item.key, item.model_alias}), None)
        if not match:
            console.print(f"[red]Modelo desconhecido:[/red] {modelo}")
            raise typer.Exit(code=2)
        wanted.append(match.key)
    elif not components.installed_models():
        recommended = next((item for item in components.models() if item.recommended), None)
        if recommended:
            wanted.append(recommended.key)
    if not sem_interlocutores:
        wanted.append(components.diarization().key)

    for key in wanted:
        if manager.is_installed(key):
            console.print(f"[green]já instalado:[/green] {key}")
            continue
        _install(key)


@app.command("remover")
def remove_command(chave: list[str] = typer.Argument(..., help="Chaves a desinstalar.")) -> None:
    """Apaga componentes já baixados."""

    from jp2subs.runtime.manager import manager

    for key in chave:
        try:
            manager.uninstall(key)
        except ValueError as exc:
            console.print(f"[red]{exc}")
            continue
        console.print(f"removido: {key}")


@app.command("ui")
def ui_command() -> None:
    """Abre a janela do aplicativo."""

    from .gui.main import launch

    launch()


@app.command("versao")
def version_command() -> None:
    """Mostra a versão."""

    console.print(f"{branding.APP_NAME} {branding.VERSION}")
    console.print(branding.EXPERIMENTAL_NOTICE)


@app.command("config")
def config_command(
    mostrar: bool = typer.Option(True, "--mostrar/--redefinir", help="Mostrar ou redefinir as preferências."),
) -> None:
    """Mostra (ou redefine) as preferências salvas."""

    from .config import config_path

    if not mostrar:
        save_settings(Settings())
        console.print(f"Preferências redefinidas em {config_path()}")
        return
    settings = load_settings()
    console.print(f"[bold]{config_path()}")
    for key, value in settings.to_dict().items():
        console.print(f"  {key} = {value}")


def _install(key: str) -> None:
    from jp2subs.runtime.download import DownloadCancelled
    from jp2subs.runtime.manager import manager

    with console.status(f"Instalando {key}...") as status:

        def report(progress) -> None:
            percent = f"{progress.percent}%" if progress.percent >= 0 else "…"
            status.update(f"{key}  {percent}  {progress.detail}")

        try:
            path = manager.install(key, on_progress=report)
        except DownloadCancelled:
            console.print(f"[yellow]cancelado:[/yellow] {key}")
            return
        except Exception as exc:  # noqa: BLE001 - report, do not traceback
            console.print(f"[red]falhou:[/red] {key} — {exc}")
            raise typer.Exit(code=1) from exc
    console.print(f"[green]instalado:[/green] {key} → {path}")


def _warn_about_setup(settings: Settings) -> None:
    missing = components.missing_essentials()
    if missing:
        names = ", ".join(item.name for item in missing)
        console.print(f"[yellow]Ainda falta instalar:[/yellow] {names} — execute 'reuniao preparar'.")
    if settings.identify_speakers:
        reason = diarize.unavailable_reason()
        if reason:
            console.print(f"[yellow]{reason}")


def _print_progress(event: ProgressEvent) -> None:
    detail = f" · {event.detail}" if event.detail else ""
    console.print(f"[dim]{event.percent:>3}%[/dim] {event.stage}: {event.message}{detail}", highlight=False)


def main() -> None:
    app()


if __name__ == "__main__":  # pragma: no cover
    main()
