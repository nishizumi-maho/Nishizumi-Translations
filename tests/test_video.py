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


def test_mux_soft_mkv_ass(monkeypatch):
    captured = _capture_run(monkeypatch)

    result = video.mux_soft("input.mkv", "subtitles.ass", "out.mkv")

    assert result == Path("out.mkv")
    assert captured["title"] == "ffmpeg mux"
    assert "-c:s" in captured["cmd"]
    assert captured["cmd"][captured["cmd"].index("-c:s") + 1] == "ass"


def test_mux_soft_mp4_srt(monkeypatch):
    captured = _capture_run(monkeypatch)

    result = video.mux_soft("input.mp4", "captions.srt", "out.mp4")

    assert result == Path("out.mp4")
    assert captured["cmd"][captured["cmd"].index("-c:s") + 1] == "mov_text"


def test_mux_soft_mp4_rejects_ass():
    with pytest.raises(ValueError, match="MP4 container does not support ASS"):
        video.mux_soft("input.mp4", "styled.ass", "out.mp4")


def test_burn_subs_builds_filter(monkeypatch):
    captured = _capture_run(monkeypatch)
    subs_path = Path("C:/Video Files/Subs:Archive/movie subs.ass")

    video.burn_subs(
        "input.mp4",
        subs_path,
        "out.mp4",
        font="My Font",
        styles={"Outline": "2"},
    )

    vf_index = captured["cmd"].index("-vf")
    filter_arg = captured["cmd"][vf_index + 1]
    assert r"subtitles=C\:/Video\ Files/Subs\:Archive/movie\ subs.ass" in filter_arg
    assert "force_style='Fontname=My Font,Outline=2'" in filter_arg


def test_ffmpeg_version(monkeypatch):
    class DummyResult:
        def __init__(self, stdout: str):
            self.stdout = stdout

    def fake_run(cmd, check, capture_output, text):
        assert cmd == ["ffmpeg", "-version"]
        return DummyResult("ffmpeg version n4.4\n")

    monkeypatch.setattr(video.subprocess, "run", fake_run)

    assert video.ffmpeg_version() == "ffmpeg version n4.4"
