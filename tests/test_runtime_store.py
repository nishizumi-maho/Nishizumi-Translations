from pathlib import Path

from jp2subs.runtime import store


def test_data_dir_honours_env_override(monkeypatch, tmp_path):
    monkeypatch.setenv(store.ENV_DATA_DIR, str(tmp_path))

    assert store.data_dir() == tmp_path
    assert store.models_dir() == tmp_path / "models"
    assert store.tools_dir() == tmp_path / "tools"
    assert store.manifest_path() == tmp_path / "components.json"


def test_ensure_dirs_creates_the_tree(monkeypatch, tmp_path):
    monkeypatch.setenv(store.ENV_DATA_DIR, str(tmp_path / "nested"))

    store.ensure_dirs()

    assert store.models_dir().is_dir()
    assert store.tools_dir().is_dir()
    assert store.cache_dir().is_dir()


def test_human_size_formats_each_unit():
    assert store.human_size(0) == "—"
    assert store.human_size(None) == "—"
    assert store.human_size(512) == "512 B"
    assert store.human_size(1024) == "1.0 KB"
    assert store.human_size(1024 ** 2 * 3) == "3.0 MB"
    assert store.human_size(int(1024 ** 3 * 2.9)) == "2.9 GB"


def test_dir_size_sums_a_tree(tmp_path):
    (tmp_path / "sub").mkdir()
    (tmp_path / "a.bin").write_bytes(b"x" * 100)
    (tmp_path / "sub" / "b.bin").write_bytes(b"y" * 50)

    assert store.dir_size(tmp_path) == 150
    assert store.dir_size(tmp_path / "a.bin") == 100
    assert store.dir_size(tmp_path / "missing") == 0


def test_remove_path_handles_files_dirs_and_absence(tmp_path):
    target_file = tmp_path / "file.txt"
    target_file.write_text("hi", encoding="utf-8")
    target_dir = tmp_path / "dir"
    (target_dir / "inner").mkdir(parents=True)

    store.remove_path(target_file)
    store.remove_path(target_dir)
    store.remove_path(tmp_path / "never-existed")

    assert not target_file.exists()
    assert not target_dir.exists()


def test_free_space_walks_up_to_an_existing_parent(tmp_path):
    assert store.free_space(tmp_path / "does" / "not" / "exist") > 0


def test_data_dir_falls_back_per_platform(monkeypatch):
    monkeypatch.delenv(store.ENV_DATA_DIR, raising=False)
    monkeypatch.setattr(store.sys, "platform", "linux")
    monkeypatch.setenv("XDG_DATA_HOME", "/tmp/xdg")

    assert store.data_dir() == Path("/tmp/xdg") / "jp2subs"
