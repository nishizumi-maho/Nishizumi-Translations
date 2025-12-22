"""Dependency management helpers for jp2subs."""
from __future__ import annotations

import json
import platform
import re
import tempfile
import zipfile
from pathlib import Path
from typing import Any, Iterable

import typer
from rich.console import Console
from rich.progress import BarColumn, Progress, TaskProgressColumn, TextColumn

from . import config

RELEASE_URL = "https://api.github.com/repos/ggml-org/llama.cpp/releases/latest"
EXECUTABLE_CANDIDATES: tuple[str, ...] = ("llama-cli.exe", "llama-server.exe")

MODEL_CATALOG: dict[str, tuple[str, str]] = {
    "1": ("TheBloke/Mistral-7B-Instruct-v0.2-GGUF", "mistral-7b-instruct-v0.2.Q4_K_M.gguf"),
    "2": ("bartowski/Qwen2.5-7B-Instruct-GGUF", "qwen2.5-7b-instruct-q4_0.gguf"),
    "3": ("TheBloke/Nous-Hermes-2-Mistral-7B-DPO-GGUF", "nous-hermes-llama3-8b.Q4_K_M.gguf"),
}


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


def _choose_asset(candidate: dict[str, Any] | None) -> dict[str, Any] | None:
    if not candidate:
        return None
    name = candidate.get("name", "")
    lowered = name.lower()
    forbidden_markers = ("cudart-llama-bin", "runtime", "meta-llama")
    if any(marker in lowered for marker in forbidden_markers):
        return None
    return candidate


def select_windows_asset(release_data: dict[str, Any]) -> dict[str, Any] | None:
    assets: Iterable[dict[str, Any]] = release_data.get("assets", [])
    ordered_patterns = [r"llama-.*-bin-win-cuda-x64\.zip", r"llama-.*-bin-win-x64\.zip"]
    for pattern in ordered_patterns:
        candidates = [a for a in assets if re.fullmatch(pattern, a.get("name", ""))]
        if candidates:
            return candidates[0]
    return None


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
    system = platform.system().lower()
    machine = platform.machine().lower()
    if "windows" not in system:
        console.print("[red]llama.cpp installer currently targets Windows binaries only.[/red]")
        raise typer.Exit(code=1)
    if "64" not in machine and "x86_64" not in machine and "amd64" not in machine:
        console.print("[red]Only x64 Windows builds are supported by the automatic installer.[/red]")
        raise typer.Exit(code=1)

    try:
        release = fetch_latest_release()
    except Exception as exc:  # pragma: no cover - network required
        console.print(f"[red]Failed to fetch release metadata:[/red] {exc}")
        raise typer.Exit(code=1)

    asset = _choose_asset(select_windows_asset(release))
    if not asset:
        console.print("[red]No suitable Windows assets found. Expected llama-*-bin-win-cuda-x64.zip or llama-*-bin-win-x64.zip.[/red]")
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
        found_files = [p.name for p in target_dir.rglob("*") if p.is_file()]
        console.print("[red]Unable to locate llama.cpp executable in downloaded archive.[/red]")
        if found_files:
            console.print("Files extracted:")
            for item in sorted(found_files):
                console.print(f" - {item}")
        console.print("Expected llama-cli.exe or llama-server.exe. Please re-run with a supported asset or install manually.")
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

        llama_model = cfg.translation.llama_model
        if not llama_model:
            issues.append("translation.llama_model is unset. Run 'jp2subs deps install-model' or download a GGUF manually.")
        elif not Path(llama_model).exists():
            issues.append(
                f"Configured llama_model not found at {llama_model}. Re-download the GGUF or update translation.llama_model."
            )

    if issues:
        for issue in issues:
            console.print(f"[red]- {issue}[/red]")
        console.print("Resolve the issues above and re-run doctor.")
        return 1

    console.print("[green]All dependency checks passed.[/green]")
    return 0


def install_model(console: Console) -> Path:
    console.print("Select a GGUF model to download:")
    options = {
        "1": "mistral-7b-instruct (Q4_K_M) – recommended",
        "2": "qwen2.5-7b-instruct (Q4)",
        "3": "nous-hermes-llama3-8b (Q4)",
        "4": "custom (Hugging Face repo)",
    }
    for key, label in options.items():
        console.print(f"[{key}] {label}")

    choice = input("Enter a choice [1-4]: ").strip() or "1"
    if choice not in options:
        console.print("[red]Invalid choice.[/red]")
        raise typer.Exit(code=1)

    if choice == "4":
        repo = input("Hugging Face repo (e.g., TheBloke/Mistral-7B-Instruct-v0.2-GGUF): ").strip()
        filename = input("GGUF filename (e.g., model.Q4_K_M.gguf): ").strip()
    else:
        repo, filename = MODEL_CATALOG[choice]

    if not repo or not filename:
        console.print("[red]Repository and filename are required.[/red]")
        raise typer.Exit(code=1)

    target_dir = config.app_config_dir() / "models"
    target_dir.mkdir(parents=True, exist_ok=True)
    dest = target_dir / Path(filename).name
    url = f"https://huggingface.co/{repo}/resolve/main/{filename}"
    console.print(f"Downloading model from {url}")
    _download_with_progress(url, dest, console)

    cfg = config.load_config()
    cfg.translation.llama_model = str(dest)
    config.save_config(cfg)

    console.print("[green]Model downloaded successfully.[/green]")
    console.print(f"Saved to: [bold]{dest}[/bold]")
    return dest
