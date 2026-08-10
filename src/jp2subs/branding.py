"""Names and links used by the GUI, the installer and the update checker.

Kept in one place so a rename does not mean hunting through string literals.
"""
from __future__ import annotations

from . import __version__

#: What the product calls itself to users.
APP_NAME = "Nishizumi Translations"
#: Short technical name: the Python package, the CLI, the config folder.
APP_ID = "jp2subs"
APP_TAGLINE = "Japanese audio and video, turned into subtitles."
PUBLISHER = "nishizumi-maho"

REPO_OWNER = "nishizumi-maho"
REPO_NAME = "Nishizumi-Translations"
REPO_URL = f"https://github.com/{REPO_OWNER}/{REPO_NAME}"
ISSUES_URL = f"{REPO_URL}/issues"
RELEASES_URL = f"{REPO_URL}/releases"
DOCS_URL = f"{REPO_URL}#readme"

VERSION = __version__


def window_title() -> str:
    return f"{APP_NAME} {VERSION}"


def about_text() -> str:
    return (
        f"{APP_NAME} {VERSION}\n\n"
        f"{APP_TAGLINE}\n\n"
        "Transcribes Japanese speech with Whisper, adds optional romaji, exports "
        "SRT/VTT/ASS, and muxes or burns the result into video with FFmpeg.\n\n"
        "Models, FFmpeg and GPU libraries are downloaded from the Components page — "
        "no manual setup required.\n\n"
        "MIT licensed. Built with PySide6, faster-whisper and FFmpeg."
    )
