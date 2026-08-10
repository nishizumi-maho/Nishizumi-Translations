from pathlib import Path

from jp2subs import config


def test_config_roundtrip(tmp_path):
    cfg = config.AppConfig()
    cfg.ffmpeg_path = "C:/ffmpeg/bin/ffmpeg.exe"
    cfg.translation.target_languages = ["en", "es"]
    path = tmp_path / "config.toml"

    saved = config.save_config(cfg, path)
    loaded = config.load_config(saved)

    assert loaded.ffmpeg_path.endswith("ffmpeg.exe")
    assert "en" in loaded.translation.target_languages


def test_config_persists_llama_binary(tmp_path):
    cfg = config.AppConfig()
    cfg.translation.llama_binary = "C:/llama/llama.exe"
    cfg.translation.llama_model = "C:/models/model.gguf"

    saved = config.save_config(cfg, tmp_path / "config.toml")
    loaded = config.load_config(saved)

    assert loaded.translation.llama_binary.endswith("llama.exe")
    assert loaded.translation.llama_model.endswith("model.gguf")


def test_app_config_dir_prefers_appdata(monkeypatch):
    fake_appdata = Path("C:/Users/test/AppData/Roaming")
    monkeypatch.setenv("APPDATA", str(fake_appdata))

    assert config.app_config_dir() == fake_appdata / "jp2subs"


def test_app_settings_roundtrip(tmp_path):
    cfg = config.AppConfig()
    cfg.app.theme = "light"
    cfg.app.check_updates_on_start = False
    cfg.app.include_prereleases = True
    cfg.app.setup_completed = True
    cfg.app.last_update_check = "2026-08-09T12:00:00+00:00"

    loaded = config.load_config(config.save_config(cfg, tmp_path / "config.toml"))

    assert loaded.app.theme == "light"
    assert loaded.app.check_updates_on_start is False
    assert loaded.app.include_prereleases is True
    assert loaded.app.setup_completed is True
    assert loaded.app.last_update_check == "2026-08-09T12:00:00+00:00"


def test_defaults_survive_a_roundtrip(tmp_path):
    cfg = config.AppConfig()
    cfg.defaults.beam_size = 7
    cfg.defaults.vad = False
    cfg.defaults.threads = 12
    cfg.defaults.compute_type = "int8"
    cfg.defaults.extra_asr_args = {"condition_on_previous_text": "false"}

    loaded = config.load_config(config.save_config(cfg, tmp_path / "config.toml"))

    assert loaded.defaults.beam_size == 7
    assert loaded.defaults.vad is False
    assert loaded.defaults.threads == 12
    assert loaded.defaults.compute_type == "int8"
    assert loaded.defaults.extra_asr_args == {"condition_on_previous_text": "false"}


def test_unknown_keys_in_config_are_ignored(tmp_path):
    path = tmp_path / "config.toml"
    path.write_text(
        '[app]\ntheme = "light"\nsomething_new = "ignored"\n\n[defaults]\nbeam_size = 3\n',
        encoding="utf-8",
    )

    loaded = config.load_config(path)

    assert loaded.app.theme == "light"
    assert loaded.defaults.beam_size == 3


def test_detect_ffmpeg_prefers_the_managed_copy(monkeypatch):
    monkeypatch.setattr(config, "_managed_ffmpeg", lambda: "C:/managed/ffmpeg.exe")
    monkeypatch.setattr(config.shutil, "which", lambda _name: "C:/path/ffmpeg.exe")

    assert config.detect_ffmpeg() == "C:/managed/ffmpeg.exe"
    # An explicit setting still wins over the managed copy.
    assert config.detect_ffmpeg("C:/custom/ffmpeg.exe") == "C:/custom/ffmpeg.exe"


def test_detect_ffmpeg_falls_back_to_path(monkeypatch):
    monkeypatch.setattr(config, "_managed_ffmpeg", lambda: None)
    monkeypatch.setattr(config.shutil, "which", lambda _name: "C:/path/ffmpeg.exe")

    assert config.detect_ffmpeg() == "C:/path/ffmpeg.exe"

