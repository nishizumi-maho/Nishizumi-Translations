"""GUI smoke tests.

These only need Qt to import; nothing here opens a window. The heavier
"build every page" check is skipped when PySide6 is unavailable so the CLI-only
install can still run the suite.
"""
import importlib

import pytest


def test_import_gui_package():
    module = importlib.import_module("jp2subs.gui")

    assert module is not None


def test_parse_extra_args_handles_types():
    from jp2subs.gui.pages.transcribe import parse_extra_args

    parsed = parse_extra_args("condition_on_previous_text=false beam=4 temp=0.5 name=whisper")

    assert parsed == {
        "condition_on_previous_text": False,
        "beam": 4,
        "temp": 0.5,
        "name": "whisper",
    }
    assert parse_extra_args("") is None
    assert parse_extra_args("no_equals_sign") is None


def test_safe_path_component_strips_separators():
    from jp2subs.gui.pages.transcribe import safe_path_component

    assert safe_path_component("Episode 01: The Start") == "Episode_01__The_Start"
    assert safe_path_component("...") == "job"


def test_legacy_widget_aliases_still_resolve():
    pytest.importorskip("PySide6")
    widgets = importlib.import_module("jp2subs.gui.widgets")

    assert widgets.PipelineTab is widgets.TranscribePage
    assert widgets.FinalizeTab is widgets.FinalizePage
    assert widgets.SettingsTab is widgets.SettingsPage
    assert widgets.MainWindow is not None


def test_legacy_worker_module_reexports():
    pytest.importorskip("PySide6")
    worker = importlib.import_module("jp2subs.gui.worker")

    assert worker.PipelineWorker is not None
    assert worker.FinalizeWorker is not None


def test_ass_colour_conversion_roundtrips():
    pytest.importorskip("PySide6")
    from PySide6 import QtGui

    from jp2subs.gui.pages.finalize import ass_color, color_from_ass

    assert ass_color(QtGui.QColor(255, 255, 255)) == "&H00FFFFFF"
    assert ass_color(QtGui.QColor(0, 0, 0), alpha_percent=50) == "&H80000000"
    assert ass_color(QtGui.QColor(255, 0, 0)) == "&H000000FF"

    assert color_from_ass("&H00FFFFFF").name() == "#ffffff"
    assert color_from_ass("&H000000FF").name() == "#ff0000"
    assert color_from_ass("garbage").name() == "#ffffff"
