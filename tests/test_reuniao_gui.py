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

    assert set(window._pages) == {"transcrever", "componentes", "sobre"}
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
    assert not page.people_spin.isEnabled()
    assert not page.names_edit.isEnabled()

    page.speakers_check.setChecked(True)
    assert page.people_spin.isEnabled()
    assert page.names_edit.isEnabled()
