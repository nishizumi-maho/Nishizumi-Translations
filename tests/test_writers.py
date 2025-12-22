from jp2subs.models import MasterDocument, Meta, Segment
from jp2subs.subtitles import render_ass, render_srt, render_vtt

SEGMENTS = [
    Segment(id=1, start=0.0, end=1.5, ja_raw="こんにちは", translations={"ja": "こんにちは", "en": "Hello"}),
    Segment(id=2, start=2.0, end=3.0, ja_raw="えっと…", translations={"ja": "えっと…", "en": "Um..."}),
]
DOC = MasterDocument(meta=Meta(source="sample"), segments=SEGMENTS)


def test_render_srt_basic():
    content = render_srt(DOC.segments, "ja")
    assert "00:00:00,000 --> 00:00:01,500" in content
    assert "こんにちは" in content


def test_render_vtt_replaces_commas():
    content = render_vtt(DOC.segments, "en")
    assert "WEBVTT" in content.splitlines()[0]
    assert "00:00:00.000 --> 00:00:01.500" in content


def test_render_ass_contains_styles():
    content = render_ass(DOC.segments, "ja")
    assert "[Script Info]" in content
    assert "Dialogue" in content
