"""Dependency management helpers for jp2subs."""
from __future__ import annotations

import json
import tempfile
import zipfile
from pathlib import Path
from typing import Any, Iterable

import typer
from rich.console import Console
from rich.progress import BarColumn, Progress, TaskProgressColumn, TextColumn

from . import config

RELEASE_URL = "https://api.github.com/repos/ggml-org/llama.cpp/releases/latest"
PREFERRED_ASSET = "bin-win-avx2-x64.zip"
FALLBACK_MARKER = "bin-win-"
EXECUTABLE_CANDIDATES: tuple[str, ...] = ("llama-cli.exe", "llama.exe", "llama-server.exe")


def _http_get(url: str, timeout: int = 30) -> bytes:
    try:
        import requests

        response = requests.get(url, timeout=timeout)
        response.raise_for_status()
        return response.content
    except ImportError:
        import urllib.request

        with urllib.request.urlopen(url, timeout=timeout) as resp:  # type: ignore[attr-defined]
            if resp.status != 200:  # pragma: no cover - urllib handles errors
                raise RuntimeError(f"HTTP error {resp.status} for {url}")
            return resp.read()


def fetch_latest_release() -> dict[str, Any]:
    raw = _http_get(RELEASE_URL)
    return json.loads(raw.decode("utf-8"))


def select_windows_asset(release_data: dict[str, Any]) -> dict[str, Any] | None:
    assets: Iterable[dict[str, Any]] = release_data.get("assets", [])
    preferred = [a for a in assets if PREFERRED_ASSET in a.get("name", "").lower()]
    if preferred:
        return preferred[0]

    fallbacks = [a for a in assets if _is_generic_windows_asset(a.get("name", ""))]
    if fallbacks:
        return fallbacks[0]
    return None


def _is_generic_windows_asset(name: str) -> bool:
    lowered = name.lower()
    return FALLBACK_MARKER in lowered and lowered.endswith("x64.zip")


def _download_with_progress(url: str, dest: Path, console: Console) -> None:
    import urllib.request

    console.print(f"Downloading [bold]{url}[/bold] -> {dest}")
    with urllib.request.urlopen(url) as response:  # type: ignore[attr-defined]
        total = response.length or 0
        downloaded = 0
        progress = Progress(
            TextColumn("{task.description}"),
            BarColumn(),
            TaskProgressColumn(),
            TextColumn("{task.fields[info]}"),
            console=console,
            transient=True,
        )
        with progress:
            task_id = progress.add_task("download", total=total, info="0 B")
            chunk_size = 1024 * 256
            dest.parent.mkdir(parents=True, exist_ok=True)
            with dest.open("wb") as out_file:
                while True:
                    chunk = response.read(chunk_size)
                    if not chunk:
                        break
                    out_file.write(chunk)
                    downloaded += len(chunk)
                    info = _format_progress_info(downloaded, total)
                    progress.update(task_id, completed=downloaded, info=info)


def _format_progress_info(downloaded: int, total: int) -> str:
    if total:
        return f"{downloaded:,} / {total:,} bytes"
    return f"{downloaded:,} bytes"


def _extract_zip(zip_path: Path, target_dir: Path) -> None:
    target_dir.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path, "r") as archive:
        archive.extractall(target_dir)


def _find_executable(root: Path) -> Path | None:
    for candidate in EXECUTABLE_CANDIDATES:
        matches = list(root.rglob(candidate))
        if matches:
            return matches[0]
    return None


def install_llama(console: Console) -> Path:
    try:
        release = fetch_latest_release()
    except Exception as exc:  # pragma: no cover - network required
        console.print(f"[red]Failed to fetch release metadata:[/red] {exc}")
        raise typer.Exit(code=1)

    asset = select_windows_asset(release)
    if not asset:
        console.print("[red]No Windows AVX2/x64 assets found in latest release.[/red]")
        raise typer.Exit(code=1)

    tag = release.get("tag_name") or "latest"
    target_dir = config.app_config_dir() / "deps" / "llama.cpp" / tag

    console.print(f"Preparing llama.cpp release [bold]{tag}[/bold]")

    with tempfile.TemporaryDirectory() as tmpdir:
        zip_path = Path(tmpdir) / asset["name"]
        _download_with_progress(asset["browser_download_url"], zip_path, console)
        _extract_zip(zip_path, target_dir)

    binary_path = _find_executable(target_dir)
    if not binary_path:
        console.print("[red]Unable to locate llama.cpp executable in downloaded archive.[/red]")
        raise typer.Exit(code=1)

    cfg = config.load_config()
    cfg.translation.llama_binary = str(binary_path)
    config.save_config(cfg)

    console.print(
        "[green]llama.cpp installed successfully.[/green]\n"
        f"Binary: [bold]{binary_path}[/bold]\n"
        "Set your GGUF model path via translation.llama_model in config.toml."
    )
    return binary_path


def doctor(console: Console) -> int:
    issues: list[str] = []
    cfg = config.load_config()

    ffmpeg_path = config.detect_ffmpeg(cfg.ffmpeg_path)
    if not ffmpeg_path:
        issues.append("ffmpeg not found. Install ffmpeg and ensure it is on PATH or set ffmpeg_path in config.toml.")
    else:
        console.print(f"[green]ffmpeg detected:[/green] {ffmpeg_path}")

    if cfg.translation.provider.lower() == "local":
        llama_binary = cfg.translation.llama_binary
        if not llama_binary:
            issues.append(
                "translation.provider=local but translation.llama_binary is unset. Run 'jp2subs deps install-llama'."
            )
        elif not Path(llama_binary).exists():
            issues.append(
                f"Configured llama_binary not found at {llama_binary}. Reinstall or update translation.llama_binary."
            )
        else:
            console.print(f"[green]llama_binary found:[/green] {llama_binary}")

    if issues:
        for issue in issues:
            console.print(f"[red]- {issue}[/red]")
        console.print("Resolve the issues above and re-run doctor.")
        return 1

    console.print("[green]All dependency checks passed.[/green]")
    return 0
