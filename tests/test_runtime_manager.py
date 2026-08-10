import json
import sys

import pytest

from jp2subs.runtime import catalog, store
from jp2subs.runtime.manager import ComponentManager, _keep_model_file, _latest_wheel, _prune_ffmpeg


@pytest.fixture
def sandbox(monkeypatch, tmp_path):
    monkeypatch.setenv(store.ENV_DATA_DIR, str(tmp_path))
    return tmp_path


@pytest.fixture
def manager(sandbox):
    return ComponentManager()


def _fake_model(sandbox, alias="large-v3"):
    model_dir = sandbox / "models" / alias
    model_dir.mkdir(parents=True)
    (model_dir / "config.json").write_text("{}", encoding="utf-8")
    (model_dir / "model.bin").write_bytes(b"0" * 32)
    return model_dir


def _fake_ffmpeg(sandbox):
    binary_dir = sandbox / "tools" / "ffmpeg" / "bin"
    binary_dir.mkdir(parents=True)
    name = "ffmpeg.exe" if sys.platform.startswith("win") else "ffmpeg"
    probe = "ffprobe.exe" if sys.platform.startswith("win") else "ffprobe"
    (binary_dir / name).write_bytes(b"0")
    (binary_dir / probe).write_bytes(b"0")
    return binary_dir / name


def test_install_paths_are_namespaced(manager, sandbox):
    model = catalog.component("model:small")
    assert manager.install_path(model) == sandbox / "models" / "small"
    assert manager.install_path(catalog.ffmpeg_component()) == sandbox / "tools" / "ffmpeg"


def test_model_needs_both_config_and_weights(manager, sandbox):
    model_dir = sandbox / "models" / "large-v3"
    model_dir.mkdir(parents=True)
    (model_dir / "config.json").write_text("{}", encoding="utf-8")

    assert not manager.is_installed("model:large-v3")

    (model_dir / "model.bin").write_bytes(b"0")
    assert manager.is_installed("model:large-v3")


def test_resolve_model_prefers_a_managed_copy(manager, sandbox):
    model_dir = _fake_model(sandbox)

    assert manager.resolve_model("large-v3") == str(model_dir)


def test_resolve_model_passes_through_unknown_names(manager):
    assert manager.resolve_model("large-v3") == "large-v3"
    assert manager.resolve_model("") == ""


def test_resolve_model_accepts_a_custom_folder(manager, tmp_path):
    custom = tmp_path / "my-ct2-model"
    custom.mkdir()

    assert manager.resolve_model(str(custom)) == str(custom)


def test_default_model_prefers_the_recommended_installed_one(manager, sandbox):
    assert manager.default_model() == "large-v3-turbo"

    _fake_model(sandbox, "small")
    assert manager.default_model() == "small"

    _fake_model(sandbox, "large-v3-turbo")
    assert manager.default_model() == "large-v3-turbo"


def test_ffmpeg_and_ffprobe_resolution(manager, sandbox):
    assert manager.ffmpeg_binary() is None

    binary = _fake_ffmpeg(sandbox)

    assert manager.ffmpeg_binary() == str(binary)
    assert manager.ffprobe_binary().endswith(("ffprobe", "ffprobe.exe"))
    assert manager.is_installed("tool:ffmpeg")


def test_missing_required_reports_ffmpeg_and_a_model(manager, sandbox, monkeypatch):
    monkeypatch.setattr("jp2subs.runtime.manager.item_ffmpeg_on_path", lambda: False)

    missing = {item.key for item in manager.missing_required()}
    assert missing == {"tool:ffmpeg", catalog.recommended_model_key()}
    assert not manager.is_ready()

    _fake_ffmpeg(sandbox)
    _fake_model(sandbox)
    manager.refresh()

    assert manager.missing_required() == []
    assert manager.is_ready()


def test_missing_required_accepts_ffmpeg_from_path(manager, sandbox, monkeypatch):
    monkeypatch.setattr("jp2subs.runtime.manager.item_ffmpeg_on_path", lambda: True)
    _fake_model(sandbox)

    assert manager.is_ready()


def test_uninstall_removes_files_and_manifest_entry(manager, sandbox):
    _fake_model(sandbox)
    manager._record("model:large-v3", sandbox / "models" / "large-v3", version="test")
    assert json.loads(store.manifest_path().read_text(encoding="utf-8"))["model:large-v3"]

    manager.uninstall("model:large-v3")

    assert not (sandbox / "models" / "large-v3").exists()
    assert "model:large-v3" not in json.loads(store.manifest_path().read_text(encoding="utf-8"))


def test_uninstall_rejects_unknown_keys(manager):
    with pytest.raises(ValueError):
        manager.uninstall("model:nope")


def test_status_reports_size_and_version(manager, sandbox):
    path = _fake_model(sandbox)
    manager._record("model:large-v3", path, version="Systran/faster-whisper-large-v3")

    status = manager.status("model:large-v3")

    assert status.installed
    assert status.size == 34
    assert status.version == "Systran/faster-whisper-large-v3"


def test_corrupt_manifest_is_ignored(manager, sandbox):
    store.ensure_dirs()
    store.manifest_path().write_text("not json", encoding="utf-8")

    assert manager.status("model:tiny").installed is False


def test_keep_model_file_filters_repo_noise():
    assert _keep_model_file("model.bin")
    assert _keep_model_file("config.json")
    assert _keep_model_file("vocabulary.txt")
    assert not _keep_model_file("README.md")
    assert not _keep_model_file(".gitattributes")
    assert not _keep_model_file("model.safetensors")
    assert not _keep_model_file("preview.png")


def test_prune_ffmpeg_keeps_only_the_binaries(tmp_path):
    binary_dir = tmp_path / "bin"
    binary_dir.mkdir()
    for name in ("ffmpeg.exe", "ffprobe.exe", "ffplay.exe", "avcodec.dll"):
        (binary_dir / name).write_bytes(b"0")
    docs = tmp_path / "doc"
    docs.mkdir()
    (docs / "ffmpeg.html").write_text("x", encoding="utf-8")

    _prune_ffmpeg(tmp_path)

    remaining = sorted(item.name for item in tmp_path.rglob("*") if item.is_file())
    assert remaining == ["avcodec.dll", "ffmpeg.exe", "ffprobe.exe"]
    assert not docs.exists()


def test_latest_wheel_picks_the_newest_matching_build(monkeypatch):
    payload = {
        "releases": {
            "12.1.0": [{"filename": "nvidia_cublas_cu12-12.1.0-win_amd64.whl", "url": "u1", "size": 1}],
            "12.9.2": [{"filename": "nvidia_cublas_cu12-12.9.2-win_amd64.whl", "url": "u2", "size": 2}],
            "12.10.0": [{"filename": "nvidia_cublas_cu12-12.10.0-win_amd64.whl", "url": "u3", "size": 3}],
            "13.0.0": [{"filename": "nvidia_cublas_cu13-13.0.0-win_amd64.whl", "url": "u4", "size": 4}],
        }
    }
    monkeypatch.setattr("jp2subs.runtime.manager.fetch_json", lambda _url: payload)
    monkeypatch.setattr(sys, "platform", "win32")

    version, url, size = _latest_wheel("nvidia-cublas-cu12", "12")

    assert (version, url, size) == ("12.10.0", "u3", 3)


def test_latest_wheel_skips_yanked_and_raises_when_empty(monkeypatch):
    payload = {
        "releases": {
            "12.1.0": [
                {"filename": "x-12.1.0-win_amd64.whl", "url": "u", "size": 1, "yanked": True},
            ]
        }
    }
    monkeypatch.setattr("jp2subs.runtime.manager.fetch_json", lambda _url: payload)
    monkeypatch.setattr(sys, "platform", "win32")

    with pytest.raises(RuntimeError):
        _latest_wheel("x", "12")
