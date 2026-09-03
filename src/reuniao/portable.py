"""Portable mode: everything the app needs, inside the app's own folder.

A locked-down work machine is exactly where a per-user install falls over —
no admin rights, a roaming profile, a policy that blocks writes under
AppData. With a ``portatil.txt`` file sitting next to the program, the speech
models, FFmpeg and the settings all live in ``dados/`` beside it instead, so
the whole folder can be dropped on a second drive or a USB stick and still
work.

Nothing here changes where the *transcripts* go: those follow the recording,
or whichever output folder was chosen.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

from jp2subs.runtime import store

#: Drop this file next to the program to turn portable mode on. Deleting it
#: sends the app back to the usual per-user folders.
MARKER_NAME = "portatil.txt"

#: Overrides the marker either way, for a shortcut or a scripted run.
ENV_FLAG = "REUNIAO_PORTATIL"

#: Everything the app installs for itself goes under here.
DATA_FOLDER = "dados"

_TRUE = {"1", "true", "sim", "yes", "on"}
_FALSE = {"0", "false", "nao", "não", "no", "off"}

#: Filled in by :func:`activate`, read by the UI so it can say what is going on.
_state: dict[str, object] = {"checked": False, "active": False, "problem": ""}


def app_dir() -> Path:
    """The folder the program lives in.

    For the packaged build that is the folder holding the executable. Running
    from a checkout it is the repository root, which makes the mode testable
    without building anything.
    """

    if getattr(sys, "frozen", False):  # PyInstaller
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[2]


def marker_path() -> Path:
    return app_dir() / MARKER_NAME


def data_dir() -> Path:
    return app_dir() / DATA_FOLDER


def components_dir() -> Path:
    return data_dir() / "componentes"


def config_dir() -> Path:
    return data_dir() / "config"


def requested() -> bool:
    """Whether portable mode was asked for, before checking it can work."""

    flag = os.environ.get(ENV_FLAG, "").strip().lower()
    if flag in _TRUE:
        return True
    if flag in _FALSE:
        return False
    return marker_path().exists()


def activate() -> bool:
    """Point the component store and the settings at the app's own folder.

    Idempotent, and safe to call from anywhere: a folder that cannot be
    written to falls back to the usual per-user locations rather than failing,
    because a read-only program folder should cost the user a worse path, not
    a crash.
    """

    if _state["checked"]:
        return bool(_state["active"])
    _state["checked"] = True

    if not requested():
        return False

    problem = _prepare(data_dir())
    if problem:
        _state["problem"] = problem
        return False

    # The store reads this before anything else, so one variable moves every
    # model, every tool and the whole download manifest.
    os.environ.setdefault(store.ENV_DATA_DIR, str(components_dir()))
    # Belt and braces: nothing should reach the Hugging Face cache, but if a
    # model name ever slips through unresolved, it lands here and not in the
    # user's home folder.
    os.environ.setdefault("HF_HOME", str(data_dir() / "cache"))

    _state["active"] = True
    return True


def is_active() -> bool:
    """True when the app is running out of its own folder."""

    if not _state["checked"]:
        activate()
    return bool(_state["active"])


def problem() -> str:
    """Why portable mode was asked for but not used. Empty when there is none."""

    if not _state["checked"]:
        activate()
    return str(_state["problem"])


def describe() -> str:
    """One line for the Components page."""

    if is_active():
        return f"Modo portátil: tudo fica em {data_dir()}"
    trouble = problem()
    if trouble:
        return f"Modo portátil pedido, mas não deu para usar — {trouble}"
    return ""


def write_marker(target: Path | None = None) -> Path:
    """Create the marker file, with a note explaining what it does."""

    path = Path(target) if target else marker_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "Este arquivo liga o modo portátil do Nishizumi Reuniões.\n"
        "\n"
        "Com ele aqui, os modelos de voz, o FFmpeg e as suas preferências ficam\n"
        f"na pasta '{DATA_FOLDER}', ao lado do programa — nada é gravado em\n"
        "AppData nem no perfil do usuário. A pasta inteira pode ser copiada para\n"
        "outro disco ou um pen drive e continua funcionando.\n"
        "\n"
        "Apague este arquivo para voltar ao comportamento normal, que guarda os\n"
        "modelos na pasta do usuário.\n",
        encoding="utf-8",
    )
    return path


def _prepare(target: Path) -> str:
    """Create *target* and prove it is writable. Returns a reason, or ''."""

    try:
        target.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        return f"não foi possível criar {target} ({exc.strerror or exc})"

    probe = target / ".escrita-ok"
    try:
        probe.write_text("ok", encoding="utf-8")
        probe.unlink()
    except OSError as exc:
        return f"a pasta {target} não aceita gravação ({exc.strerror or exc})"
    return ""


def _reset_for_tests() -> None:
    """Forget what was decided, so a test can set a different folder up."""

    _state.update({"checked": False, "active": False, "problem": ""})


if __name__ == "__main__":  # pragma: no cover - packaging helper
    # python -m reuniao.portable <pasta>  ->  drops the marker into a build.
    target = Path(sys.argv[1]) if len(sys.argv) > 1 else app_dir()
    print(write_marker(target / MARKER_NAME))
