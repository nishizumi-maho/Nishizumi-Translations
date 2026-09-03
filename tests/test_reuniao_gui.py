"""GUI smoke tests. Nothing here opens a real window."""
from __future__ import annotations

import importlib

import pytest


def test_the_package_imports_without_qt():
    assert importlib.import_module("reuniao.gui") is not None


def test_the_window_builds_with_every_page(monkeypatch, tmp_path):
    pytest.importorskip("PySide6")
    from PySide6 import QtWidgets

    from jp2subs.runtime import store

    monkeypatch.setenv("APPDATA", str(tmp_path / "config"))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    monkeypatch.setenv(store.ENV_DATA_DIR, str(tmp_path / "components"))
    QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

    from reuniao.gui.window import MainWindow

    window = MainWindow()

    assert set(window._pages) == {"transcrever", "revisar", "componentes", "sobre"}
    # Nothing is installed under the temporary folder, so the app says so.
    assert window.readiness_chip.text() == "Falta baixar"
    assert window.transcribe_page.banner.isVisibleTo(window.transcribe_page)


def test_the_transcribe_page_only_takes_media_files(monkeypatch, tmp_path):
    pytest.importorskip("PySide6")
    from PySide6 import QtWidgets

    monkeypatch.setenv("APPDATA", str(tmp_path / "config"))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

    from reuniao.gui.pages.transcrever import TranscribePage

    page = TranscribePage()
    recording = tmp_path / "reuniao.m4a"
    recording.write_bytes(b"audio")
    document = tmp_path / "pauta.docx"
    document.write_bytes(b"nao e midia")

    monkeypatch.setattr(
        "reuniao.gui.pages.transcrever.QtWidgets.QMessageBox.information",
        lambda *_args, **_kwargs: None,
    )
    page._add_paths([str(recording), str(document)])

    assert [path.name for path in page.queue.paths()] == ["reuniao.m4a"]
    # The queue only appears once there is something in it.
    assert page.queue.isVisibleTo(page)


def test_the_speaker_fields_follow_the_checkbox(monkeypatch, tmp_path):
    pytest.importorskip("PySide6")
    from PySide6 import QtWidgets

    monkeypatch.setenv("APPDATA", str(tmp_path / "config"))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

    from reuniao.gui.pages.transcrever import TranscribePage

    page = TranscribePage()

    page.speakers_check.setChecked(False)
    assert not page.separation_combo.isEnabled()
    assert not page.names_edit.isEnabled()

    page.speakers_check.setChecked(True)
    assert page.separation_combo.isEnabled()
    assert page.names_edit.isEnabled()


def test_the_glossary_reaches_the_settings(monkeypatch, tmp_path):
    """The field is what makes the glossary exist for anyone but a programmer."""

    pytest.importorskip("PySide6")
    from PySide6 import QtWidgets

    monkeypatch.setenv("APPDATA", str(tmp_path / "config"))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

    from reuniao.gui.pages.transcrever import TranscribePage

    page = TranscribePage()
    page.glossary_edit.setPlainText("João Nakagawa\n\n  OKR  \nAcme")

    settings = page._collect_settings()

    assert settings.glossary == ["João Nakagawa", "OKR", "Acme"]


def test_a_finished_run_is_handed_to_the_review_page(monkeypatch, tmp_path):
    pytest.importorskip("PySide6")
    from PySide6 import QtWidgets

    monkeypatch.setenv("APPDATA", str(tmp_path / "config"))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

    from reuniao.gui.pages.transcrever import TranscribePage
    from reuniao.model import Transcript, Utterance
    from reuniao.pipeline import Result

    page = TranscribePage()
    received: list = []
    page.transcript_ready.connect(received.append)

    transcript = Transcript(source="/x/reuniao.mp3", duration=10, utterances=[Utterance(0, 5, "oi")])
    page._on_finished(Result(transcript=transcript, files=[tmp_path / "reuniao.txt"]))

    assert received and received[0] is transcript
