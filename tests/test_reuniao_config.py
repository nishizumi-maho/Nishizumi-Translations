"""Saved preferences: defaults, clamping and round-trips."""
from __future__ import annotations

from reuniao.config import (
    DEFAULT_PROMPT,
    Settings,
    load_settings,
    parse_speaker_names,
    save_settings,
)


def test_defaults_are_meeting_shaped():
    settings = Settings()

    assert settings.identify_speakers is True
    assert settings.layout == "blocos"
    assert settings.speaker_count == 0  # work it out automatically
    assert settings.avoid_repetition is True
    assert "português do Brasil" in DEFAULT_PROMPT


def test_out_of_range_and_unknown_values_are_pulled_back():
    settings = Settings.from_dict(
        {
            "layout": "sei-la",
            "device": "tpu",
            "beam_size": 999,
            "speaker_count": -4,
            "clustering_threshold": 9.0,
            "speaker_names": ["Ana", "  ", "João"],
            "campo_que_nao_existe": True,
        }
    )

    assert settings.layout == "blocos"
    assert settings.device == "auto"
    assert settings.beam_size == 20
    assert settings.speaker_count == 0
    assert settings.clustering_threshold == 1.5
    assert settings.speaker_names == ["Ana", "João"]


def test_settings_survive_a_save_and_load(tmp_path):
    path = tmp_path / "config.json"
    settings = Settings()
    settings.speaker_names = ["Ana", "João"]
    settings.layout = "linhas"
    settings.also_srt = True

    save_settings(settings, path)
    loaded = load_settings(path)

    assert loaded.speaker_names == ["Ana", "João"]
    assert loaded.layout == "linhas"
    assert loaded.also_srt is True


def test_a_damaged_config_falls_back_to_the_defaults(tmp_path):
    path = tmp_path / "config.json"
    path.write_text("{isso não é json", encoding="utf-8")

    assert load_settings(path).layout == "blocos"


def test_missing_config_needs_no_file(tmp_path):
    assert load_settings(tmp_path / "nao-existe.json").model == ""


def test_names_are_split_on_commas_semicolons_and_lines():
    assert parse_speaker_names(" Ana, João;Carla \n Beto ") == ["Ana", "João", "Carla", "Beto"]
    assert parse_speaker_names("") == []
