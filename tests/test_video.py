from pathlib import Path

import pytest

from jp2subs import video


def _capture_run(monkeypatch):
    captured = {}

    def fake_run(cmd, title):
        captured["cmd"] = cmd
        captured["title"] = title

    monkeypatch.setattr(video, "run_command", fake_run)
    return captured


def test_build_out_path_softcode_same_name_with_suffix():
    out_path = video.build_out_path(
        Path("Movie.mp4"),
        Path("subtitle.srt"),
        Path("outdir"),
        same_name=True,
        suffix=".soft",
        container="mkv",
        mode="softcode",
    )

    assert out_path == Path("outdir/Movie.soft.mkv")


def test_validate_subtitle_format_mp4_rejects_ass():
    with pytest.raises(ValueError, match="MP4 não suporta ASS; use MKV ou converta"):
        video.validate_subtitle_format("mp4", "styled.ass")


def test_run_ffmpeg_mux_soft_builds_command(monkeypatch):
    captured = _capture_run(monkeypatch)

    result = video.run_ffmpeg_mux_soft(
        "input.mp4", "captions.srt", "out.mp4", container="mp4", lang="pt-BR"
    )

    assert result == Path("out.mp4")
    assert captured["cmd"][captured["cmd"].index("-c:s") + 1] == "mov_text"
    assert "language=pt-BR" in captured["cmd"]


def test_run_ffmpeg_burn_uses_ass_filter(monkeypatch):
    captured = _capture_run(monkeypatch)
    subs_path = Path("C:/Video Files/Subs:Archive/movie subs.ass")

    video.run_ffmpeg_burn(
        "input.mp4",
        subs_path,
        "out.mp4",
        codec="libx264",
        crf=18,
        preset="slow",
        font="My Font",
        styles={"Outline": "2"},
    )

    vf_index = captured["cmd"].index("-vf")
    filter_arg = captured["cmd"][vf_index + 1]
    assert r"ass=C\:/Video\ Files/Subs\:Archive/movie\ subs.ass" in filter_arg
    assert "force_style='Fontname=My Font,Outline=2'" in filter_arg


def test_run_ffmpeg_burn_uses_subtitles_filter(monkeypatch):
    captured = _capture_run(monkeypatch)
    subs_path = Path("show.srt")

    video.run_ffmpeg_burn(
        "input.mp4",
        subs_path,
        "out.mp4",
        codec="libx265",
        crf=20,
        preset="medium",
    )

    vf_index = captured["cmd"].index("-vf")
    filter_arg = captured["cmd"][vf_index + 1]
    assert filter_arg.startswith("subtitles=")
    assert "ass=" not in filter_arg
    assert "-crf" in captured["cmd"]
    assert captured["cmd"][captured["cmd"].index("-crf") + 1] == "20"


def test_ffmpeg_version(monkeypatch):
    class DummyResult:
        def __init__(self, stdout: str):
            self.stdout = stdout

    def fake_run(cmd, check, capture_output, text):
        assert cmd == ["ffmpeg", "-version"]
        return DummyResult("ffmpeg version n4.4\n")

    monkeypatch.setattr(video.subprocess, "run", fake_run)

    assert video.ffmpeg_version() == "ffmpeg version n4.4"
