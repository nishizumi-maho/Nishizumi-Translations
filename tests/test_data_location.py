"""Choosing where models and tools are installed."""
import json

import pytest

from jp2subs.runtime import catalog, store
from jp2subs.runtime.manager import ComponentManager


@pytest.fixture
def sandbox(monkeypatch, tmp_path):
    """A fake profile: a config folder for the pointer, and a default data dir."""

    monkeypatch.delenv(store.ENV_DATA_DIR, raising=False)
    monkeypatch.setenv("APPDATA", str(tmp_path / "config"))
    monkeypatch.setattr(store.sys, "platform", "linux")
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "share"))
    return tmp_path


def _installed_model(root, alias="small"):
    model_dir = root / "models" / alias
    model_dir.mkdir(parents=True)
    (model_dir / "config.json").write_text("{}", encoding="utf-8")
    (model_dir / "model.bin").write_bytes(b"0" * 64)
    return model_dir


def test_default_location_is_used_without_a_pointer(sandbox):
    assert store.data_dir() == sandbox / "share" / "jp2subs"
    assert store.configured_data_dir() is None
    assert not store.is_custom_location()


def test_pointer_file_moves_every_derived_path(sandbox):
    target = sandbox / "disk-d" / "jp2subs"

    store.set_data_dir(target)

    assert store.data_dir() == target
    assert store.models_dir() == target / "models"
    assert store.tools_dir() == target / "tools"
    assert store.manifest_path() == target / "components.json"
    assert store.is_custom_location()
    assert store.models_dir().is_dir()


def test_pointer_file_is_readable_json(sandbox):
    target = sandbox / "disk-d" / "jp2subs"

    store.set_data_dir(target)

    payload = json.loads(store.location_file().read_text(encoding="utf-8"))
    assert payload == {"data_dir": str(target)}


def test_env_override_wins_over_the_saved_folder(sandbox, monkeypatch):
    store.set_data_dir(sandbox / "disk-d" / "jp2subs")
    monkeypatch.setenv(store.ENV_DATA_DIR, str(sandbox / "portable"))

    assert store.data_dir() == sandbox / "portable"
    assert store.env_override() == sandbox / "portable"


def test_going_back_to_the_default_removes_the_pointer(sandbox):
    store.set_data_dir(sandbox / "disk-d" / "jp2subs")

    store.set_data_dir(None)

    assert not store.location_file().exists()
    assert store.data_dir() == store.default_data_dir()


def test_a_broken_pointer_falls_back_to_the_default(sandbox):
    pointer = store.location_file()
    pointer.parent.mkdir(parents=True, exist_ok=True)
    pointer.write_text("{ not json", encoding="utf-8")

    assert store.data_dir() == store.default_data_dir()


def test_switching_folders_carries_the_downloads_across(sandbox):
    _installed_model(store.data_dir())
    old = store.data_dir()
    target = sandbox / "disk-d" / "jp2subs"

    store.set_data_dir(target, move_existing=True)

    assert (target / "models" / "small" / "model.bin").read_bytes() == b"0" * 64
    assert not old.exists()


def test_switching_folders_can_leave_the_downloads_behind(sandbox):
    _installed_model(store.data_dir())
    old = store.data_dir()

    store.set_data_dir(sandbox / "disk-d" / "jp2subs", move_existing=False)

    assert (old / "models" / "small" / "model.bin").exists()
    assert not (store.data_dir() / "models" / "small").exists()


def test_move_data_copies_file_by_file_when_the_target_is_in_use(sandbox):
    source = sandbox / "from"
    target = sandbox / "to"
    (source / "models" / "small").mkdir(parents=True)
    (source / "models" / "small" / "model.bin").write_bytes(b"x" * 200)
    (source / "components.json").write_text("{}", encoding="utf-8")
    # A leftover file makes the fast rename impossible, forcing the copy loop.
    target.mkdir()
    (target / "stale.txt").write_text("old", encoding="utf-8")

    seen = []
    store.move_data(source, target, on_progress=lambda done, total, name: seen.append((done, total)))

    assert (target / "models" / "small" / "model.bin").read_bytes() == b"x" * 200
    assert not source.exists()
    assert seen and seen[-1][0] == seen[-1][1] > 0


def test_move_data_overwrites_files_left_by_an_interrupted_move(sandbox):
    source = sandbox / "from"
    target = sandbox / "to"
    source.mkdir()
    (source / "components.json").write_text("new", encoding="utf-8")
    target.mkdir()
    (target / "components.json").write_text("half-moved", encoding="utf-8")

    store.move_data(source, target)

    assert (target / "components.json").read_text(encoding="utf-8") == "new"


def test_validate_location_rejects_a_relative_path(sandbox):
    assert "full path" in store.validate_location("models")


def test_validate_location_rejects_a_file(sandbox):
    target = sandbox / "notes.txt"
    target.write_text("hi", encoding="utf-8")

    assert "not a folder" in store.validate_location(target)


def test_validate_location_rejects_a_folder_holding_other_files(sandbox):
    busy = sandbox / "documents"
    busy.mkdir()
    (busy / "thesis.docx").write_text("mine", encoding="utf-8")

    problem = store.validate_location(busy)

    assert "already holds other files" in problem
    assert str(busy / "jp2subs") in problem


def test_validate_location_accepts_an_existing_component_folder(sandbox):
    target = sandbox / "disk-d" / "jp2subs"
    (target / "models").mkdir(parents=True)

    assert store.validate_location(target) == ""


def test_validate_location_rejects_nesting_inside_the_current_folder(sandbox):
    assert "inside the current one" in store.validate_location(store.data_dir() / "deeper")


def test_validate_location_rejects_a_parent_of_the_current_folder(sandbox):
    store.ensure_dirs()

    assert "contains the current one" in store.validate_location(store.data_dir().parent)


def test_set_data_dir_refuses_an_unusable_folder(sandbox):
    with pytest.raises(ValueError):
        store.set_data_dir("relative/path")


def test_rebase_repoints_the_manifest_after_a_move(sandbox):
    manager = ComponentManager()
    _installed_model(store.data_dir())
    manager._record("model:small", store.data_dir() / "models" / "small")
    target = sandbox / "disk-d" / "jp2subs"

    store.set_data_dir(target, move_existing=True)
    manager.rebase()

    recorded = json.loads(store.manifest_path().read_text(encoding="utf-8"))
    assert recorded["model:small"]["path"] == str(target / "models" / "small")
    assert manager.is_installed("model:small")
    assert manager.model_path("small") == manager.install_path(catalog.component("model:small"))
