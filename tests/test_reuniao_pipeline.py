"""The run from end to end, with the heavy engines stubbed out."""
from __future__ import annotations

import pytest

from reuniao import diarize, media, pipeline, transcribe
from reuniao.config import Settings
from reuniao.model import Segment, SpeakerSpan, Word
from reuniao.pipeline import Cancelled, Job, Runner


def _words(text: str, start: float, step: float = 0.5) -> list[Word]:
    return [
        Word(start=start + index * step, end=start + (index + 1) * step, text=f" {word}")
        for index, word in enumerate(text.split())
    ]


SEGMENTS = [
    Segment(0.0, 2.0, "bom dia pessoal", _words("bom dia pessoal", 0.0)),
    Segment(2.5, 4.5, "vamos ao primeiro ponto", _words("vamos ao primeiro ponto", 2.5)),
]


@pytest.fixture
def stubbed(monkeypatch, tmp_path):
    """A recording that needs no FFmpeg and a Whisper that needs no model."""

    source = tmp_path / "reuniao.m4a"
    source.write_bytes(b"nao importa: o ffmpeg esta simulado")

    def fake_prepare(src, workdir, **_kwargs):
        target = tmp_path / "saida" / "audio16k.wav"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(b"RIFF....WAVE")
        return target

    monkeypatch.setattr(media, "prepare_audio", fake_prepare)
    monkeypatch.setattr(pipeline.media, "prepare_audio", fake_prepare)
    monkeypatch.setattr(pipeline.media, "probe_duration", lambda _path: 4.5)
    monkeypatch.setattr(pipeline.transcribe, "transcribe", lambda _audio, **_kw: list(SEGMENTS))
    monkeypatch.setattr(transcribe, "transcribe", lambda _audio, **_kw: list(SEGMENTS))
    return source, tmp_path / "saida"


def _no_diarization(monkeypatch, reason="modelos ausentes"):
    monkeypatch.setattr(pipeline.diarize, "unavailable_reason", lambda: reason)


def _fake_diarization(monkeypatch, spans):
    monkeypatch.setattr(pipeline.diarize, "unavailable_reason", lambda: "")
    monkeypatch.setattr(pipeline.media, "read_wav_mono", lambda _path: [0.0, 0.1])
    monkeypatch.setattr(pipeline.diarize, "diarize", lambda _samples, **_kw: list(spans))


def test_a_plain_run_writes_the_transcript(stubbed, monkeypatch):
    source, out = stubbed
    _no_diarization(monkeypatch)
    settings = Settings()
    settings.model = "tiny"

    result = Runner().run(Job(source=source, settings=settings, output_dir=out))

    assert result.text_file == out / "reuniao.txt"
    assert result.text_file.exists()
    assert result.transcript.diarized is False
    assert result.transcript.notes  # it says why the speakers are missing
    # The 16 kHz working copy is cleaned up after a successful run.
    assert not (out / "audio16k.wav").exists()


def test_speakers_reach_the_transcript(stubbed, monkeypatch):
    source, out = stubbed
    _fake_diarization(monkeypatch, [SpeakerSpan(0, 2.2, 0), SpeakerSpan(2.2, 5.0, 1)])
    settings = Settings()
    settings.model = "tiny"
    settings.speaker_names = ["Ana"]

    result = Runner().run(Job(source=source, settings=settings, output_dir=out))

    transcript = result.transcript
    assert transcript.diarized is True
    assert transcript.speaker_names == ["Ana", "Interlocutor 2"]
    assert [item.speaker for item in transcript.utterances] == [0, 1]
    assert "Ana" in result.text_file.read_text(encoding="utf-8-sig")


def test_the_extra_formats_share_the_transcript_name(stubbed, monkeypatch):
    source, out = stubbed
    _no_diarization(monkeypatch)
    settings = Settings()
    settings.model = "tiny"
    settings.also_srt = settings.also_vtt = settings.also_json = True
    (out).mkdir(parents=True, exist_ok=True)
    (out / "reuniao.txt").write_text("de uma execução anterior", encoding="utf-8")

    result = Runner().run(Job(source=source, settings=settings, output_dir=out))

    assert [item.name for item in result.files] == [
        "reuniao (2).txt",
        "reuniao (2).srt",
        "reuniao (2).vtt",
        "reuniao (2).json",
    ]
    assert (out / "reuniao.txt").read_text(encoding="utf-8") == "de uma execução anterior"


def test_progress_covers_every_stage_and_ends_at_100(stubbed, monkeypatch):
    source, out = stubbed
    _fake_diarization(monkeypatch, [SpeakerSpan(0, 5, 0)])
    events = []
    settings = Settings()
    settings.model = "tiny"

    Runner(on_progress=events.append).run(Job(source=source, settings=settings, output_dir=out))

    assert {event.stage for event in events} == {"Preparar", "Transcrever", "Interlocutores", "Salvar"}
    assert events[-1].percent == 100


def test_cancelling_stops_the_run_and_leaves_no_transcript(stubbed, monkeypatch):
    source, out = stubbed
    _no_diarization(monkeypatch)
    runner = Runner()
    settings = Settings()
    settings.model = "tiny"

    def cancel_midway(_audio, **_kwargs):
        runner.cancel()
        return list(SEGMENTS)

    monkeypatch.setattr(pipeline.transcribe, "transcribe", cancel_midway)

    with pytest.raises(Cancelled):
        runner.run(Job(source=source, settings=settings, output_dir=out))

    assert not (out / "reuniao.txt").exists()


def test_a_missing_recording_is_reported_before_anything_runs(tmp_path):
    with pytest.raises(FileNotFoundError):
        Runner().run(Job(source=tmp_path / "nao-existe.mp3", settings=Settings()))


def test_speaker_identification_can_simply_be_turned_off(stubbed, monkeypatch):
    source, out = stubbed
    monkeypatch.setattr(
        pipeline.diarize,
        "unavailable_reason",
        lambda: pytest.fail("não deveria consultar a diarização"),
    )
    settings = Settings()
    settings.model = "tiny"
    settings.identify_speakers = False

    result = Runner().run(Job(source=source, settings=settings, output_dir=out))

    assert result.transcript.diarized is False
    assert result.transcript.notes == []


def test_diarize_reports_why_it_is_unavailable():
    # Whatever is missing on this machine, the reason is never silent.
    reason = diarize.unavailable_reason()
    assert reason == "" or "interlocutores" in reason.lower()
