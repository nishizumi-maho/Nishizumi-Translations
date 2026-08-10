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
