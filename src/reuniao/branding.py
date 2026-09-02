"""Names and links, kept in one place so a rename stays a one-file change."""
from __future__ import annotations

from . import __version__

#: What the product calls itself to users.
APP_NAME = "Nishizumi Reuniões"
#: Short technical name: the Python package, the CLI, the config folder.
APP_ID = "reuniao"
APP_TAGLINE = "Transcrição de reuniões em português do Brasil."
PUBLISHER = "nishizumi-maho"

REPO_OWNER = "nishizumi-maho"
REPO_NAME = "Nishizumi-Translations"
REPO_URL = f"https://github.com/{REPO_OWNER}/{REPO_NAME}"
ISSUES_URL = f"{REPO_URL}/issues"
RELEASES_URL = f"{REPO_URL}/releases"

#: Shown all over the UI: this build is a side experiment, not the main app.
EXPERIMENTAL_NOTICE = (
    "Versão experimental. Ela transcreve reuniões e nada mais — sem tradução, "
    "sem legendas em vídeo, sem edição."
)

VERSION = __version__


def window_title() -> str:
    return f"{APP_NAME} {VERSION} (experimental)"


def about_text() -> str:
    return (
        f"{APP_NAME} {VERSION}\n\n"
        f"{APP_TAGLINE}\n\n"
        "Transcreve o áudio de uma reunião com o Whisper, separa quem falou o quê "
        "e salva tudo em um .txt com os horários de fala.\n\n"
        "Os modelos, o FFmpeg e as bibliotecas de GPU são baixados pela própria "
        "página de Componentes — nada precisa ser instalado à mão.\n\n"
        "Tudo roda no seu computador: o áudio nunca sai da máquina.\n\n"
        "Licença MIT. Feito com PySide6, faster-whisper, sherpa-onnx e FFmpeg."
    )
