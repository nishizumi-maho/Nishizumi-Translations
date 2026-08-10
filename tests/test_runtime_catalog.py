from jp2subs.runtime import catalog


def test_every_model_declares_a_repo_and_alias():
    for model in catalog.models():
        assert model.repo_id, f"{model.key} has no Hugging Face repo"
        assert model.model_alias, f"{model.key} has no faster-whisper alias"
        assert model.approx_size > 0
        assert model.is_model


def test_component_keys_are_unique():
    keys = [item.key for item in catalog.all_components()]

    assert len(keys) == len(set(keys))


def test_exactly_one_recommended_model():
    recommended = [model for model in catalog.models() if model.recommended]

    assert len(recommended) == 1
    assert catalog.recommended_model_key() == recommended[0].key


def test_ffmpeg_is_required_and_has_a_source():
    ffmpeg = catalog.ffmpeg_component()

    assert ffmpeg.required
    assert ffmpeg.url.startswith("https://")
    assert ffmpeg.key == "tool:ffmpeg"


def test_model_lookup_by_alias_and_key():
    assert catalog.model_for_alias("large-v3").key == "model:large-v3"
    assert catalog.model_for_alias("LARGE-V3").key == "model:large-v3"
    assert catalog.model_for_alias("model:tiny").key == "model:tiny"
    assert catalog.model_for_alias("nonsense") is None
    assert catalog.model_for_alias("") is None


def test_component_lookup():
    assert catalog.component("model:small").name == "Whisper Small"
    assert catalog.component("does-not-exist") is None


def test_cuda_pack_is_windows_x64_only(monkeypatch):
    monkeypatch.setattr(catalog, "is_windows", lambda: False)
    assert catalog.cuda_component() is None

    monkeypatch.setattr(catalog, "is_windows", lambda: True)
    monkeypatch.setattr(catalog, "is_x64", lambda: True)
    cuda = catalog.cuda_component()
    assert cuda is not None
    assert cuda.wheels
