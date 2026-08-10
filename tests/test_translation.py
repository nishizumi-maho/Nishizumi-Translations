import pytest

from jp2subs.config import AppConfig
from jp2subs.models import MasterDocument, Meta, Segment
from jp2subs.translation import (
    DEEPL,
    OFFLINE,
    OPENAI,
    DeepLProvider,
    OpenAICompatibleProvider,
    available_engines,
    build_provider,
    is_translation_available,
    languages,
    parse_numbered,
    translate_document,
)
from jp2subs.translation.providers import Cancelled, _blank_safe


class FakeProvider:
    """Records what it was asked to translate and echoes a tagged string."""

    name = "fake"

    def __init__(self):
        self.calls: list[tuple[tuple[str, ...], str]] = []

    def translate(self, lines, target, *, is_cancelled=None):
        self.calls.append((tuple(lines), target.code))
        return [f"{target.code}:{line}" if line.strip() else "" for line in lines]


def _doc(count: int = 3) -> MasterDocument:
    return MasterDocument(
        meta=Meta(source="test"),
        segments=[
            Segment(id=index + 1, start=float(index), end=float(index + 1), ja_raw=f"行{index + 1}")
            for index in range(count)
        ],
    )


# -- languages -------------------------------------------------------------


def test_language_lookup_is_forgiving():
    assert languages.get("en").name == "English"
    assert languages.get("PT-br").code == "pt-BR"
    assert languages.get("pt_BR").code == "pt-BR"
    assert languages.get("nope") is None
    assert languages.get("") is None


def test_language_codes_are_unique():
    codes = [item.code for item in languages.LANGUAGES]
    assert len(codes) == len(set(codes))


def test_every_language_has_an_nllb_code():
    for item in languages.LANGUAGES:
        assert item.nllb and "_" in item.nllb, item.code


def test_resolve_many_dedupes_and_skips_unknown():
    resolved = languages.resolve_many(["en", "en", "zzz", "pt-BR"])

    assert [item.code for item in resolved] == ["en", "pt-BR"]


def test_deepl_supported_is_a_subset():
    supported = languages.deepl_supported()

    assert all(item.deepl for item in supported)
    assert len(supported) < len(languages.LANGUAGES)


# -- document orchestration ------------------------------------------------


def test_translate_document_fills_every_language():
    doc = _doc()
    provider = FakeProvider()

    translate_document(doc, ["en", "pt-BR"], provider=provider)

    for segment in doc.segments:
        assert segment.translations["en"] == f"en:{segment.ja_raw}"
        assert segment.translations["pt-BR"] == f"pt-BR:{segment.ja_raw}"


def test_translate_document_reports_progress():
    doc = _doc(5)
    events = []

    translate_document(doc, ["en"], provider=FakeProvider(), block_size=2, on_progress=events.append)

    assert events
    assert all(event.stage == "Translate" for event in events)
    assert events[-1].percent == 92  # top of the Translate range
    assert events[0].percent < events[-1].percent


def test_translate_document_batches_by_block_size():
    doc = _doc(5)
    provider = FakeProvider()

    translate_document(doc, ["en"], provider=provider, block_size=2)

    assert [len(call[0]) for call in provider.calls] == [2, 2, 1]


def test_translate_document_requires_a_language():
    with pytest.raises(ValueError):
        translate_document(_doc(), [], provider=FakeProvider())

    with pytest.raises(ValueError):
        translate_document(_doc(), ["klingon"], provider=FakeProvider())


def test_translate_document_stops_when_cancelled():
    doc = _doc(10)

    with pytest.raises(Cancelled):
        translate_document(
            doc, ["en"], provider=FakeProvider(), block_size=2, is_cancelled=lambda: True
        )


def test_translate_document_handles_an_empty_document():
    doc = MasterDocument(meta=Meta(source="test"), segments=[])

    assert translate_document(doc, ["en"], provider=FakeProvider()) is doc


def test_translate_document_accepts_language_objects():
    doc = _doc(1)

    translate_document(doc, [languages.get("es")], provider=FakeProvider())

    assert doc.segments[0].translations["es"]


# -- providers -------------------------------------------------------------


def test_blank_safe_keeps_positions():
    payload, indexes = _blank_safe(["a", "", "  ", "b"])

    assert payload == ["a", "b"]
    assert indexes == [0, 3]


def test_parse_numbered_reads_various_separators():
    assert parse_numbered("1. one\n2) two\n3 - three", 3) == ["one", "two", "three"]


def test_parse_numbered_falls_back_to_line_order():
    assert parse_numbered("one\ntwo", 2) == ["one", "two"]


def test_parse_numbered_pads_missing_lines():
    assert parse_numbered("1. only", 3) == ["only", "", ""]


def test_parse_numbered_ignores_out_of_range_indexes():
    assert parse_numbered("9. stray\n1. good", 2) == ["good", ""]


def test_deepl_picks_the_host_from_the_key():
    assert "api-free.deepl.com" in DeepLProvider(api_key="abc:fx").endpoint
    assert "api.deepl.com" in DeepLProvider(api_key="abc").endpoint


def test_deepl_requires_a_key_and_a_supported_language():
    with pytest.raises(RuntimeError, match="API key"):
        DeepLProvider(api_key="").translate(["行"], languages.get("en"))

    with pytest.raises(RuntimeError, match="does not offer"):
        DeepLProvider(api_key="abc").translate(["行"], languages.get("th"))


def test_deepl_skips_the_network_for_blank_input():
    assert DeepLProvider(api_key="abc").translate(["", "  "], languages.get("en")) == ["", ""]


def test_openai_provider_builds_its_endpoint():
    provider = OpenAICompatibleProvider(base_url="http://localhost:1234/v1/")

    assert provider.endpoint == "http://localhost:1234/v1/chat/completions"


def test_openai_provider_parses_a_reply(monkeypatch):
    captured = {}

    def fake_post(url, payload, *, headers=None, timeout=None):
        captured["url"] = url
        captured["payload"] = payload
        return {"choices": [{"message": {"content": "1. Hello\n2. World"}}]}

    monkeypatch.setattr("jp2subs.translation.providers.post_json", fake_post)
    provider = OpenAICompatibleProvider(api_key="k", model="test-model")

    result = provider.translate(["こんにちは", "世界"], languages.get("en"))

    assert result == ["Hello", "World"]
    assert captured["payload"]["model"] == "test-model"
    assert "English" in captured["payload"]["messages"][0]["content"]


def test_openai_provider_raises_without_choices(monkeypatch):
    monkeypatch.setattr(
        "jp2subs.translation.providers.post_json", lambda *a, **k: {"error": "nope"}
    )

    with pytest.raises(RuntimeError, match="no choices"):
        OpenAICompatibleProvider().translate(["行"], languages.get("en"))


# -- engine selection ------------------------------------------------------


def test_available_engines_reports_readiness(monkeypatch):
    monkeypatch.setattr("jp2subs.translation.engine.manager.has_translation_model", lambda: False)
    cfg = AppConfig()

    engines = {engine.key: engine for engine in available_engines(cfg)}

    assert set(engines) == {OFFLINE, DEEPL, OPENAI}
    assert not engines[OFFLINE].ready
    assert "Components" in engines[OFFLINE].reason
    assert not engines[DEEPL].ready

    cfg.translation.deepl_api_key = "key"
    engines = {engine.key: engine for engine in available_engines(cfg)}
    assert engines[DEEPL].ready


def test_is_translation_available_follows_the_engines(monkeypatch):
    monkeypatch.setattr("jp2subs.translation.engine.manager.has_translation_model", lambda: False)
    cfg = AppConfig()
    cfg.translation.openai_base_url = ""

    ok, reason = is_translation_available(cfg)
    assert ok is False
    assert reason

    monkeypatch.setattr("jp2subs.translation.engine.manager.has_translation_model", lambda: True)
    ok, _ = is_translation_available(cfg)
    assert ok is True


def test_build_provider_selects_by_name(monkeypatch):
    cfg = AppConfig()
    cfg.translation.deepl_api_key = "abc:fx"
    cfg.translation.openai_base_url = "http://localhost:1234/v1"

    assert isinstance(build_provider(DEEPL, cfg), DeepLProvider)
    assert isinstance(build_provider(OPENAI, cfg), OpenAICompatibleProvider)


def test_build_provider_explains_a_missing_offline_model(monkeypatch):
    monkeypatch.setattr("jp2subs.translation.engine.manager.translation_model_path", lambda: None)

    with pytest.raises(RuntimeError, match="not installed"):
        build_provider(OFFLINE, AppConfig())
