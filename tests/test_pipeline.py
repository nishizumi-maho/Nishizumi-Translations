from pathlib import Path

import pytest

from jp2subs import pipeline
from jp2subs.gui.widgets import parse_extra_args
from jp2subs.models import MasterDocument, Meta, Segment


class DummyJob:
    def __init__(self, source: Path, workdir: Path):
        self.source = source
        self.workdir = workdir
        self.mono = False
        self.model_size = "tiny"
        self.vad = True
        self.beam_size = 1
        self.best_of = None
        self.patience = None
        self.length_penalty = None
        self.word_timestamps = True
        self.threads = None
        self.compute_type = None
        self.extra_asr_args = None
        self.generate_romaji = False
        self.fmt = "srt"


def _dummy_doc() -> MasterDocument:
    return MasterDocument(meta=Meta(source="test"), segments=[Segment(id=1, start=0, end=1, ja_raw="こんにちは")])


def test_pipeline_passes_subprocess_callback(tmp_path, monkeypatch):
    source = tmp_path / "episode.mp4"
    source.write_text("data", encoding="utf-8")
    workdir = tmp_path / "work"
    registered = []

    def fake_ingest(path, dest, mono=False, on_progress=None, register_subprocess=None):
        assert path == source
        assert register_subprocess is not None
        register_subprocess("proc")
        dest.mkdir(parents=True, exist_ok=True)
        audio_path = dest / "audio.flac"
        audio_path.write_text("audio", encoding="utf-8")
        return audio_path

    monkeypatch.setattr(pipeline.audio, "ingest_media", fake_ingest)
    monkeypatch.setattr(pipeline.asr, "transcribe_audio", lambda *args, **kwargs: _dummy_doc())
    monkeypatch.setattr(pipeline.io_mod, "save_master", lambda doc, path: path.write_text("{}", encoding="utf-8"))
    monkeypatch.setattr(
        pipeline.subtitles,
        "write_subtitles",
        lambda doc, path, fmt, lang, secondary=None: path.write_text("subs", encoding="utf-8"),
    )

    runner = pipeline.PipelineRunner(pipeline.PipelineCallbacks(on_subprocess=registered.append))
    outputs = runner.run(DummyJob(source, workdir))

    assert registered == ["proc"]
    assert outputs == [workdir / "subs_ja.srt"]


def test_pipeline_cancel_before_run(tmp_path):
    source = tmp_path / "episode.mp4"
    source.write_text("data", encoding="utf-8")
    runner = pipeline.PipelineRunner()
    runner.cancel()

    with pytest.raises(RuntimeError, match="Job cancelled"):
        runner.run(DummyJob(source, tmp_path / "work"))


def test_parse_extra_args_coerces_common_scalar_values():
    parsed = parse_extra_args("temperature=0.2 suppress_blank=true beam_size=3 name=value")

    assert parsed == {
        "temperature": 0.2,
        "suppress_blank": True,
        "beam_size": 3,
        "name": "value",
    }
