"""What the app offers to download, and what it insists on."""
from __future__ import annotations

import pytest

from jp2subs.runtime import catalog
from jp2subs.runtime.catalog import ComponentKind
from jp2subs.runtime.manager import EMBEDDING_MODEL, SEGMENTATION_MODEL, _pick_onnx, manager
from reuniao import components
from reuniao.diarize import COMPONENT_KEY


def test_the_diarization_pack_resolves_without_cluttering_the_subtitle_app():
    pack = catalog.component(COMPONENT_KEY)

    assert pack is not None
    assert pack.kind is ComponentKind.DIARIZATION
    assert len(pack.urls) == 2
    # The subtitle app's Components page lists all_components(); this is not there.
    assert all(item.key != COMPONENT_KEY for item in catalog.all_components())


def test_the_pack_installs_into_its_own_folder():
    pack = catalog.component(COMPONENT_KEY)

    path = manager.install_path(pack)

    assert path.parent.name == "diarization"


def test_the_full_model_is_preferred_over_its_quantised_sibling(tmp_path):
    (tmp_path / "model.int8.onnx").write_bytes(b"quantizado")
    (tmp_path / "model.onnx").write_bytes(b"completo")
    (tmp_path / "voz.onnx").write_bytes(b"embedding")

    segmentation = _pick_onnx(tmp_path, ("model.onnx",))
    embedding = _pick_onnx(tmp_path, (), exclude={segmentation})

    assert segmentation.name == "model.onnx"
    assert embedding.name == "voz.onnx"


def test_the_installed_pack_uses_fixed_filenames():
    # The diarizer looks these up by name, whatever the archives called them.
    assert SEGMENTATION_MODEL == "segmentation.onnx"
    assert EMBEDDING_MODEL == "embedding.onnx"


def test_only_models_that_suit_portuguese_are_offered():
    keys = {item.key for item in components.models()}

    assert "model:large-v3-turbo" in keys
    assert "model:tiny" in keys
    # Japanese fine-tunes and the English distil model have no place here.
    assert "model:kotoba-v2" not in keys
    assert "model:large-v2-ja" not in keys
    assert "model:distil-large-v3" not in keys


def test_every_offered_item_speaks_portuguese():
    for item in components.all_components():
        assert item.summary
        assert not item.summary.startswith("Extracts audio")


def test_the_page_is_grouped_and_leads_with_the_essentials():
    titles = [title for title, _hint, _items in components.page_sections()]

    assert titles[0] == "Essenciais"
    assert "Modelos de transcrição" in titles
    assert "Interlocutores" in titles


def test_nothing_can_be_transcribed_until_ffmpeg_and_a_model_are_there(monkeypatch):
    monkeypatch.setattr(components.manager, "is_installed", lambda _key: False)
    monkeypatch.setattr(components, "_ffmpeg_on_path", lambda: False)

    missing = {item.key for item in components.missing_essentials()}

    assert missing == {components.ffmpeg().key, "model:large-v3-turbo"}
    assert components.is_ready() is False


def test_ffmpeg_already_on_the_path_counts_as_installed(monkeypatch):
    monkeypatch.setattr(components.manager, "is_installed", lambda key: key.startswith("model:"))
    monkeypatch.setattr(components, "_ffmpeg_on_path", lambda: True)

    assert components.missing_essentials() == []
    assert components.is_ready() is True


def test_sizes_are_shown_the_way_a_download_dialog_should():
    assert components.human_size(1024 * 1024 * 1536) == "1.5 GB"
    assert components.human_size(0) == "—"


@pytest.mark.parametrize("attribute", ["name", "summary"])
def test_the_diarization_pack_is_described_for_a_meeting(attribute):
    text = getattr(components.diarization(), attribute).lower()

    assert "interlocutor" in text or "vozes" in text
