"""Models installed through Hugging Face search rather than shipped in the catalog."""
import pytest

from jp2subs.runtime import catalog, store
from jp2subs.runtime.manager import ComponentManager

REPO = "kotoba-tech/kotoba-whisper-v2.0-faster"


@pytest.fixture
def manager(monkeypatch, tmp_path):
    monkeypatch.setenv(store.ENV_DATA_DIR, str(tmp_path))
    return ComponentManager()


def _place(manager, component):
    path = manager.install_path(component)
    path.mkdir(parents=True, exist_ok=True)
    (path / "config.json").write_text("{}", encoding="utf-8")
    (path / "model.bin").write_bytes(b"0" * 16)
    return path


def test_custom_slug_is_filesystem_safe():
    assert catalog.custom_slug(REPO) == "kotoba-tech__kotoba-whisper-v2.0-faster"
    assert catalog.custom_slug("owner/name") == "owner__name"
    assert catalog.custom_slug("///") == "custom-model"


def test_custom_component_shape():
    component = catalog.custom_model(REPO, approx_size=1234)

    assert component.custom
    assert component.is_model
    assert component.key == f"model:hf:{REPO}"
    assert component.repo_id == REPO
    assert component.family is catalog.ModelFamily.CUSTOM
    assert component.approx_size == 1234


def test_custom_model_round_trips_through_the_manifest(manager):
    component = catalog.custom_model(REPO, approx_size=99, name=REPO)
    path = _place(manager, component)
    manager._record(component.key, path, version=REPO, component=component)
    manager.refresh()

    rebuilt = manager.custom_components()
    assert [item.repo_id for item in rebuilt] == [REPO]
    assert manager.is_installed(component.key)
    assert manager._resolve_component(component.key).repo_id == REPO


def test_custom_models_appear_alongside_catalog_models(manager):
    component = catalog.custom_model(REPO, name=REPO)
    manager._record(component.key, _place(manager, component), component=component)
    manager.refresh()

    keys = [item.key for item in manager.installed_models()]
    assert component.key in keys


def test_resolve_model_matches_slug_and_repo_id(manager):
    component = catalog.custom_model(REPO, name=REPO)
    path = _place(manager, component)
    manager._record(component.key, path, component=component)
    manager.refresh()

    assert manager.resolve_model(component.model_alias) == str(path)
    assert manager.resolve_model(REPO) == str(path)
    assert manager.resolve_model(component.key) == str(path)


def test_unknown_custom_model_passes_through(manager):
    assert manager.resolve_model("someone/not-installed") == "someone/not-installed"


def test_uninstalling_a_custom_model_clears_it(manager):
    component = catalog.custom_model(REPO, name=REPO)
    manager._record(component.key, _place(manager, component), component=component)
    manager.refresh()

    manager.uninstall(component.key)

    assert not manager.is_installed(component.key)
    assert manager.custom_components() == []


def test_translation_model_is_not_a_speech_model(manager):
    component = catalog.default_translation_model()
    _place(manager, component)
    manager.refresh()

    assert manager.is_installed(component.key)
    assert manager.has_translation_model()
    assert manager.translation_model_path() == manager.install_path(component)
    assert component.key not in [item.key for item in manager.installed_models()]


def test_translation_model_lives_under_models_translation(manager):
    component = catalog.default_translation_model()

    assert manager.install_path(component).parent == store.models_dir() / "translation"


def test_japanese_models_are_in_the_catalog():
    japanese = [item for item in catalog.models() if item.family is catalog.ModelFamily.JAPANESE]

    assert {item.model_alias for item in japanese} == {"kotoba-v2", "kotoba-bilingual", "large-v2-ja"}
    for item in japanese:
        assert item.repo_id
        assert catalog.model_for_alias(item.model_alias) is item


def test_models_by_family_covers_every_model():
    grouped = catalog.models_by_family()
    total = sum(len(items) for items in grouped.values())

    assert total == len(catalog.models())
    assert catalog.ModelFamily.JAPANESE in grouped
