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

