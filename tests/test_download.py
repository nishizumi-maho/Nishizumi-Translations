import tarfile
import zipfile

import pytest

from jp2subs.runtime import download


def _zip_with(tmp_path, entries):
    archive = tmp_path / "bundle.zip"
    with zipfile.ZipFile(archive, "w") as handle:
        for name, content in entries.items():
            handle.writestr(name, content)
    return archive


def test_extract_archive_unpacks_a_zip(tmp_path):
    archive = _zip_with(tmp_path, {"bin/ffmpeg.exe": "binary", "README": "text"})
    target = tmp_path / "out"

    download.extract_archive(archive, target)

    assert (target / "bin" / "ffmpeg.exe").read_text() == "binary"


def test_extract_archive_refuses_path_traversal(tmp_path):
    archive = tmp_path / "evil.zip"
    with zipfile.ZipFile(archive, "w") as handle:
        handle.writestr("../escaped.txt", "nope")

    with pytest.raises(RuntimeError, match="outside target"):
        download.extract_archive(archive, tmp_path / "out")

    assert not (tmp_path / "escaped.txt").exists()


def test_extract_archive_refuses_tar_traversal(tmp_path):
    payload = tmp_path / "payload.txt"
    payload.write_text("nope", encoding="utf-8")
    archive = tmp_path / "evil.tar"
    with tarfile.open(archive, "w") as handle:
        handle.add(payload, arcname="../escaped.txt")

    with pytest.raises(RuntimeError, match="outside target"):
        download.extract_archive(archive, tmp_path / "out")


def test_extract_archive_rejects_unknown_formats(tmp_path):
    blob = tmp_path / "file.bin"
    blob.write_bytes(b"not an archive")

    with pytest.raises(RuntimeError, match="Unsupported archive"):
        download.extract_archive(blob, tmp_path / "out")


def test_flatten_single_root_collapses_a_wrapper_folder(tmp_path):
    inner = tmp_path / "ffmpeg-7.1-win64" / "bin"
    inner.mkdir(parents=True)
    (inner / "ffmpeg.exe").write_text("x", encoding="utf-8")

    download.flatten_single_root(tmp_path)

    assert (tmp_path / "bin" / "ffmpeg.exe").exists()
    assert not (tmp_path / "ffmpeg-7.1-win64").exists()


def test_flatten_single_root_leaves_multi_entry_dirs_alone(tmp_path):
    (tmp_path / "a").mkdir()
    (tmp_path / "b").mkdir()

    download.flatten_single_root(tmp_path)

    assert (tmp_path / "a").exists()
    assert (tmp_path / "b").exists()


def test_find_first_searches_recursively(tmp_path):
    nested = tmp_path / "one" / "two"
    nested.mkdir(parents=True)
    (nested / "ffprobe.exe").write_text("x", encoding="utf-8")

    assert download.find_first(tmp_path, ("ffmpeg.exe", "ffprobe.exe")).name == "ffprobe.exe"
    assert download.find_first(tmp_path, ("missing",)) is None


def test_progress_defaults_are_display_ready():
    progress = download.Progress(label="model.bin")

    assert progress.percent == 0
    assert progress.total == 0
    assert progress.eta_seconds is None


def test_download_file_honours_cancellation(tmp_path):
    def always_cancelled() -> bool:
        return True

    with pytest.raises(download.DownloadCancelled):
        download.download_file(
            "https://example.invalid/never-requested",
            tmp_path / "out.bin",
            is_cancelled=always_cancelled,
        )


def _flaky_replace(failures: int, calls: list):
    """A Path.replace that denies access the first *failures* times."""

    from pathlib import Path

    real = Path.replace

    def attempt(self, target):
        calls.append(str(self))
        if len(calls) <= failures:
            raise PermissionError(13, "Acesso negado")
        return real(self, target)

    return attempt


def test_replace_waits_out_a_scanner_holding_the_file(tmp_path, monkeypatch):
    """The rename that fails right after a big download is retried, not lost."""

    from pathlib import Path

    calls: list = []
    monkeypatch.setattr(Path, "replace", _flaky_replace(3, calls))
    monkeypatch.setattr(download.time, "sleep", lambda _seconds: None)

    source = tmp_path / "ffmpeg-0.zip.part"
    source.write_bytes(b"conteudo baixado")
    dest = tmp_path / "ffmpeg-0.zip"

    download.replace_atomically(source, dest)

    assert dest.read_bytes() == b"conteudo baixado"
    assert not source.exists()
    assert len(calls) == 4  # three refusals, then it went through


def test_replace_falls_back_to_copying_when_the_rename_never_works(tmp_path, monkeypatch):
    from pathlib import Path

    monkeypatch.setattr(
        Path, "replace", lambda self, target: (_ for _ in ()).throw(PermissionError(13, "Acesso negado"))
    )
    monkeypatch.setattr(download.time, "sleep", lambda _seconds: None)

    source = tmp_path / "grande.zip.part"
    source.write_bytes(b"163 MB de ffmpeg")
    dest = tmp_path / "grande.zip"

    download.replace_atomically(source, dest)

    # A copy still gets the user their file, even with the source locked.
    assert dest.read_bytes() == b"163 MB de ffmpeg"


def test_replace_reraises_anything_that_is_not_a_lock(tmp_path, monkeypatch):
    from pathlib import Path

    monkeypatch.setattr(
        Path, "replace", lambda self, target: (_ for _ in ()).throw(IsADirectoryError(21, "boom"))
    )
    monkeypatch.setattr(download.time, "sleep", lambda _seconds: None)

    source = tmp_path / "a.part"
    source.write_bytes(b"x")

    with pytest.raises(OSError):
        download.replace_atomically(source, tmp_path / "a")


def test_replace_tree_retries_then_moves_the_component_folder(tmp_path, monkeypatch):
    from pathlib import Path

    calls: list = []
    monkeypatch.setattr(Path, "replace", _flaky_replace(2, calls))
    monkeypatch.setattr(download.time, "sleep", lambda _seconds: None)

    staging = tmp_path / "ffmpeg.incomplete"
    staging.mkdir()
    (staging / "ffmpeg.exe").write_bytes(b"binario")
    final = tmp_path / "ffmpeg"

    download.replace_tree(staging, final)

    assert (final / "ffmpeg.exe").read_bytes() == b"binario"
    assert len(calls) == 3
