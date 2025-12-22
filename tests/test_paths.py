from pathlib import Path

from jp2subs import paths


def test_strip_quotes_and_normalize():
    raw = '"C:/media/file.mkv"'
    normalized = paths.normalize_input_path(raw)
    assert normalized.name == "file.mkv"


def test_default_workdir_and_coerce(tmp_path):
    media = tmp_path / "show.mkv"
    media.write_text("data", encoding="utf-8")
    workdir = paths.default_workdir_for_input(media)
    assert workdir.name == "show"
    assert workdir.parent.name == "_jobs"

    coerced = paths.coerce_workdir(media)
    assert coerced.name == "show"
    assert coerced.parent == tmp_path

