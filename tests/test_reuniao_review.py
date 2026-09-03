"""Reading a transcript back, and lining it up with the recording."""
from __future__ import annotations

import json

import pytest

from reuniao import review
from reuniao.model import Transcript, Utterance, assign_names
from reuniao.writers import write_json


def _transcript() -> Transcript:
    return Transcript(
        source="/gravacoes/reuniao.mp3",
        duration=30,
        model="large-v3-turbo",
        diarized=True,
        speaker_names=assign_names(2, ["Ana"]),
        utterances=[
            Utterance(1.0, 10.0, "Bom dia a todos.", 0, confidence=0.95, weight=4),
            Utterance(11.0, 20.0, "não entendi bem", 1, confidence=0.3, weight=3),
            Utterance(21.0, 30.0, "Fechado então.", 0, confidence=0.9, weight=3),
        ],
    )


def test_a_finished_run_becomes_a_review():
    result = review.from_transcript(_transcript())

    assert [turn.speaker for turn in result.turns] == ["Ana", "Interlocutor 2", "Ana"]
    assert result.turns[1].uncertain is True
    assert result.title == "reuniao.mp3"


def test_a_saved_json_round_trips_through_the_review(tmp_path):
    written = write_json(_transcript(), tmp_path / "reuniao.json")

    result = review.from_json(written)

    assert len(result.turns) == 3
    assert result.turns[0].text == "Bom dia a todos."
    assert result.turns[1].uncertain is True


def test_the_recording_is_found_beside_the_transcript_after_a_move(tmp_path):
    """People move folders; the path stored at transcription time goes stale."""

    transcript = _transcript()
    written = write_json(transcript, tmp_path / "reuniao.json")
    moved = tmp_path / "reuniao.mp3"
    moved.write_bytes(b"audio")

    result = review.from_json(written)

    assert result.source == moved
    assert result.has_audio is True


def test_a_missing_recording_is_reported_rather_than_guessed(tmp_path):
    written = write_json(_transcript(), tmp_path / "reuniao.json")

    result = review.from_json(written)

    assert result.has_audio is False


def test_the_wrong_kind_of_json_is_refused(tmp_path):
    path = tmp_path / "outra-coisa.json"
    path.write_text(json.dumps({"algo": "diferente"}), encoding="utf-8")

    with pytest.raises(ValueError):
        review.from_json(path)


def test_the_playhead_finds_the_turn_being_spoken():
    result = review.from_transcript(_transcript())

    assert result.turn_at(0.5) is None  # before anyone speaks
    assert result.turn_at(5.0) == 0
    assert result.turn_at(15.0) == 1
    # In the silence between turns the last speaker stays highlighted, rather
    # than the list going blank every time somebody pauses.
    assert result.turn_at(10.5) == 0
    assert result.turn_at(999.0) == 2


def test_the_page_lists_the_turns_and_filters_them(tmp_path, monkeypatch):
    pytest.importorskip("PySide6")
    from PySide6 import QtWidgets

    monkeypatch.setenv("APPDATA", str(tmp_path / "config"))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

    from reuniao.gui.pages.revisar import ReviewPage

    page = ReviewPage()
    page.show_review(review.from_transcript(_transcript()))

    assert page.list.count() == 3

    page._filter("fechado")
    hidden = [page.list.item(row).isHidden() for row in range(page.list.count())]
    assert hidden == [True, True, False]
    assert page.match_label.text() == "1 de 3"

    page._filter("")
    assert not any(page.list.item(row).isHidden() for row in range(page.list.count()))


def test_the_page_survives_a_build_without_the_audio_module(tmp_path, monkeypatch):
    """A Linux box with no PulseAudio still gets a usable transcript list."""

    pytest.importorskip("PySide6")
    from PySide6 import QtWidgets

    monkeypatch.setenv("APPDATA", str(tmp_path / "config"))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

    import reuniao.gui.pages.revisar as page_module

    monkeypatch.setattr(page_module, "AUDIO_AVAILABLE", False)
    page = page_module.ReviewPage()
    page.show_review(review.from_transcript(_transcript()))

    assert page.list.count() == 3
    assert not page.play_btn.isEnabled()
    assert "não tem o componente de áudio" in page.audio_note.text()
