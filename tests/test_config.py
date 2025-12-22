from pathlib import Path

from jp2subs import config


def test_config_roundtrip(tmp_path):
    cfg = config.AppConfig()
    cfg.ffmpeg_path = "C:/ffmpeg/bin/ffmpeg.exe"
    cfg.translation.target_languages = ["pt-BR", "en"]
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

