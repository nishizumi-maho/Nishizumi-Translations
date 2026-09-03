"""Keeping the hour-long half of the work when the fast half fails."""
from __future__ import annotations

from reuniao import cache
from reuniao.config import Settings
from reuniao.model import Segment, Word


def _settings() -> Settings:
    settings = Settings()
    settings.model = "large-v3-turbo"
    return settings


def _segments() -> list[Segment]:
    words = [Word(0.0, 0.5, " bom", 0.9), Word(0.5, 1.0, " dia", 0.8)]
    return [Segment(0.0, 1.0, "bom dia", words, 0.85)]


def test_a_saved_transcription_comes_back_intact(tmp_path, monkeypatch):
    monkeypatch.setenv("JP2SUBS_DATA_DIR", str(tmp_path / "dados"))
    recording = tmp_path / "reuniao.m4a"
    recording.write_bytes(b"audio")
    settings = _settings()

    cache.save(recording, settings, _segments())
    restored = cache.load(recording, settings)

    assert restored is not None
    assert restored[0].text == "bom dia"
    assert restored[0].confidence == 0.85
    assert [word.text for word in restored[0].words] == [" bom", " dia"]
    assert restored[0].words[0].confidence == 0.9


def test_changing_a_setting_that_changes_the_result_invalidates_it(tmp_path, monkeypatch):
    monkeypatch.setenv("JP2SUBS_DATA_DIR", str(tmp_path / "dados"))
    recording = tmp_path / "reuniao.m4a"
    recording.write_bytes(b"audio")
    settings = _settings()
    cache.save(recording, settings, _segments())

    for field, value in (
        ("model", "large-v3"),
        ("beam_size", 9),
        ("vad", False),
        ("initial_prompt", "outro contexto"),
        ("glossary", ["Acme"]),
    ):
        other = _settings()
        setattr(other, field, value)
        assert cache.load(recording, other) is None, f"{field} deveria invalidar o cache"


def test_editing_the_recording_invalidates_it(tmp_path, monkeypatch):
    monkeypatch.setenv("JP2SUBS_DATA_DIR", str(tmp_path / "dados"))
    recording = tmp_path / "reuniao.m4a"
    recording.write_bytes(b"audio")
    settings = _settings()
    cache.save(recording, settings, _segments())

    recording.write_bytes(b"outro audio, bem diferente")

    assert cache.load(recording, settings) is None


def test_nothing_saved_means_nothing_found(tmp_path, monkeypatch):
    monkeypatch.setenv("JP2SUBS_DATA_DIR", str(tmp_path / "dados"))
    recording = tmp_path / "nunca-transcrita.m4a"
    recording.write_bytes(b"audio")

    assert cache.load(recording, _settings()) is None


def test_a_damaged_cache_file_is_ignored_rather_than_trusted(tmp_path, monkeypatch):
    monkeypatch.setenv("JP2SUBS_DATA_DIR", str(tmp_path / "dados"))
    recording = tmp_path / "reuniao.m4a"
    recording.write_bytes(b"audio")
    settings = _settings()
    cache.save(recording, settings, _segments())
    cache.path_for(recording, settings).write_text("{isto não é json", encoding="utf-8")

    assert cache.load(recording, settings) is None


def test_clearing_removes_the_files(tmp_path, monkeypatch):
    monkeypatch.setenv("JP2SUBS_DATA_DIR", str(tmp_path / "dados"))
    recording = tmp_path / "reuniao.m4a"
    recording.write_bytes(b"audio")
    cache.save(recording, _settings(), _segments())

    assert cache.stored_size() > 0
    assert cache.clear() == 1
    assert cache.stored_size() == 0
