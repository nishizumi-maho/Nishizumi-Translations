from pathlib import Path

from typer.testing import CliRunner

from jp2subs import cli
from jp2subs.models import MasterDocument, Meta, Segment

runner = CliRunner()


def _dummy_doc() -> MasterDocument:
    return MasterDocument(meta=Meta(source="test"), segments=[Segment(id=1, start=0, end=1, ja_raw="こんにちは")])


def test_wizard_fails_for_missing_input():
    result = runner.invoke(cli.app, ["wizard"], input="/no/such/file.mp4\n")

    assert result.exit_code != 0
    assert "not found" in result.output.lower()


def test_wizard_runs_pipeline(tmp_path, monkeypatch):
    media = tmp_path / "episode.mp4"
    media.write_text("data", encoding="utf-8")

    workdir = tmp_path / "custom_workdir"

    calls: list[str] = []

    def fake_ingest(path: Path, dest: Path, mono: bool = False) -> Path:
        calls.append("ingest")
        dest.mkdir(parents=True, exist_ok=True)
        out = dest / "audio.flac"
        out.write_text("audio", encoding="utf-8")
        return out

    def fake_transcribe(audio_path: Path, **_: object) -> MasterDocument:
        calls.append("transcribe")
        return _dummy_doc()

    def fake_romanize(doc: MasterDocument) -> MasterDocument:
        calls.append("romanize")
        doc.add_romaji(["konnichiwa"])
        return doc

    def fake_write_subtitles(doc: MasterDocument, path: Path, fmt: str, lang: str, secondary: str | None = None):
        calls.append("export")
        path.write_text(f"{fmt}-{lang}-{secondary or ''}", encoding="utf-8")
        return path

    monkeypatch.setattr(cli.audio, "ingest_media", fake_ingest)
    monkeypatch.setattr(cli.asr, "transcribe_audio", fake_transcribe)
    monkeypatch.setattr(cli.romanizer, "romanize_segments", fake_romanize)
    monkeypatch.setattr(cli.subtitles, "write_subtitles", fake_write_subtitles)

    inputs = "\n".join(
        [
            str(media),
            str(workdir),
            "2",  # stereo
            "",  # model_size default
            "",  # beam_size default
            "",  # vad default (on)
            "1",  # device auto
            "y",  # romaji
            "1",  # format srt
            "",  # output type default
        ]
    )

    result = runner.invoke(cli.app, ["wizard"], input=inputs + "\n")

    assert result.exit_code == 0, result.output
    assert calls == ["ingest", "transcribe", "romanize", "export"]

    exported = workdir / "subs_ja.srt"
    assert exported.exists()


def test_wizard_handles_transcription_only(tmp_path, monkeypatch):
    media = tmp_path / "episode.mp4"
    media.write_text("data", encoding="utf-8")

    workdir = tmp_path / "custom_workdir"

    calls: list[str] = []

    def fake_ingest(path: Path, dest: Path, mono: bool = False) -> Path:
        calls.append("ingest")
        dest.mkdir(parents=True, exist_ok=True)
        out = dest / "audio.flac"
        out.write_text("audio", encoding="utf-8")
        return out

    def fake_transcribe(audio_path: Path, **_: object) -> MasterDocument:
        calls.append("transcribe")
        return _dummy_doc()

    def fake_write_subtitles(doc: MasterDocument, path: Path, fmt: str, lang: str, secondary: str | None = None):
        calls.append("export")
        path.write_text(f"{fmt}-{lang}-{secondary or ''}", encoding="utf-8")
        return path

    monkeypatch.setattr(cli.audio, "ingest_media", fake_ingest)
    monkeypatch.setattr(cli.asr, "transcribe_audio", fake_transcribe)
    monkeypatch.setattr(cli.romanizer, "romanize_segments", lambda doc: doc)
    monkeypatch.setattr(cli.subtitles, "write_subtitles", fake_write_subtitles)

    inputs = "\n".join(
        [
            str(media),
            str(workdir),
            "2",  # stereo
            "",  # model_size default
            "",  # beam_size default
            "",  # vad default (on)
            "1",  # device auto
            "n",  # romaji
            "1",  # format srt
            "",  # output type default
        ]
    )

    result = runner.invoke(cli.app, ["wizard"], input=inputs + "\n")

    assert result.exit_code == 0, result.output
    assert calls == ["ingest", "transcribe", "export"]

    exported = workdir / "subs_ja.srt"
    assert exported.exists()
