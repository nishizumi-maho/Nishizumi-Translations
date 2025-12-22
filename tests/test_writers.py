from jp2subs.models import MasterDocument, Meta, Segment
from jp2subs.subtitles import _wrap_text, render_ass, render_srt, render_vtt, segment_payload

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


def test_wrap_text_japanese_without_spaces():
    text = "これは日本語のテキストでスペースがありませんが、適切に改行されます。さらに長くして改行を確認します。"
    lines = _wrap_text(text, max_chars_per_line=20, max_lines=2, lang="ja")
    assert len(lines) == 2
    assert all(len(line) <= 20 for line in lines)


def test_bilingual_two_fixed_lines():
    segment = Segment(
        id=3,
        start=4.0,
        end=5.0,
        ja_raw="さようなら",
        translations={"ja": "さようなら", "en": "Goodbye"},
    )
    lines = segment_payload(segment, "en", "ja")
    assert len(lines) == 2
    assert lines[0] == "さようなら"
    assert lines[1] == "Goodbye"
    assert "/" not in "".join(lines)
