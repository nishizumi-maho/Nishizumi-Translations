from pathlib import Path

from typer.testing import CliRunner

from jp2subs import cli, io
from jp2subs.models import MasterDocument, Meta, Segment

runner = CliRunner()


def _dummy_doc() -> MasterDocument:
    return MasterDocument(meta=Meta(source="test"), segments=[Segment(id=1, start=0, end=1, ja_raw="こんにちは")])


def test_batch_creates_cached_workdirs(tmp_path, monkeypatch):
    input_dir = tmp_path / "inputs"
    input_dir.mkdir()
    media_file = input_dir / "episode.mp4"
    media_file.write_text("data", encoding="utf-8")

    workdir = tmp_path / "workdir"

    calls: dict[str, int] = {stage: 0 for stage in cli.BATCH_STAGES}

    def fake_ingest(path: Path, dest: Path, mono: bool = False) -> Path:
        calls["ingest"] += 1
        dest.mkdir(parents=True, exist_ok=True)
        audio_out = dest / "audio.flac"
        audio_out.write_text("audio", encoding="utf-8")
        return audio_out

    def fake_transcribe(audio_path: Path, **_: object) -> MasterDocument:
        calls["transcribe"] += 1
        return _dummy_doc()

    def fake_romanize(doc: MasterDocument) -> MasterDocument:
        calls["romanize"] += 1
        doc.add_romaji(["konnichiwa"])
        return doc

    def fake_translate(doc: MasterDocument, target_langs, **_: object) -> MasterDocument:
        calls["translate"] += 1
        for seg in doc.segments:
            for lang in target_langs:
                seg.translations[lang] = "hello"
        return doc

    def fake_write_subtitles(doc: MasterDocument, path: Path, fmt: str, lang: str, secondary: str | None = None):
        calls["export"] += 1
        path.write_text(f"{fmt}-{lang}-{secondary or ''}", encoding="utf-8")
        return path

    monkeypatch.setattr(cli.audio, "ingest_media", fake_ingest)
    monkeypatch.setattr(cli.asr, "transcribe_audio", fake_transcribe)
    monkeypatch.setattr(cli.romanizer, "romanize_segments", fake_romanize)
    monkeypatch.setattr(cli.translation, "translate_document", fake_translate)
    monkeypatch.setattr(cli.subtitles, "write_subtitles", fake_write_subtitles)

    result = runner.invoke(
        cli.app,
        [
            "batch",
            str(input_dir),
            "--workdir",
            str(workdir),
            "--ext",
            "mp4",
            "--to",
            "pt-BR",
            "--mode",
            "llm",
            "--provider",
            "local",
        ],
    )

    assert result.exit_code == 0, result.output

    workdir_path = cli._workdir_for_media(workdir, media_file)
    for stage in cli.BATCH_STAGES:
        assert (workdir_path / f".{stage}.done").exists()
    master_doc = io.load_master(io.master_path_from_workdir(workdir_path))
    assert master_doc.segments[0].translations.get("pt-BR") == "hello"
    assert all(count == 1 for count in calls.values())

    second = runner.invoke(
        cli.app,
        [
            "batch",
            str(input_dir),
            "--workdir",
            str(workdir),
            "--ext",
            "mp4",
            "--to",
            "pt-BR",
            "--mode",
            "llm",
            "--provider",
            "local",
        ],
    )

    assert second.exit_code == 0, second.output
    assert all(count == 1 for count in calls.values())
