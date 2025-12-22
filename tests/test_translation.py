import pytest

from jp2subs import translation
from jp2subs.models import MasterDocument, Meta, Segment


def _make_doc() -> MasterDocument:
    meta = Meta(source="unittest")
    segments = [
        Segment(id=1, start=0.0, end=1.0, ja_raw="こんにちは"),
        Segment(id=2, start=1.0, end=2.0, ja_raw="ありがとう"),
    ]
    return MasterDocument(meta=meta, segments=segments)


def test_preserves_id_count_and_alignment():
    doc = _make_doc()

    translated = translation.translate_document(doc, target_langs=["en"], provider="echo")

    outputs = [seg.translations.get("en") for seg in translated.segments]
    assert outputs == ["こんにちは", "ありがとう"]


def test_missing_outputs_are_retried_and_padded(monkeypatch):
    class MissingProvider(translation.TranslationProvider):
        def __init__(self):
            self.calls = 0

        def translate_block(self, prompt, lines, source_lang, target_lang, glossary=None):
            self.calls += 1
            # Always drop the second ID to trigger retries and padding
            return [lines[0].split("\t", 1)[0] + "\tfirst"]

    provider = MissingProvider()
    monkeypatch.setattr(translation, "_provider_from_name", lambda name: provider)

    doc = _make_doc()
    translated = translation.translate_document(doc, target_langs=["en"], provider="anything")

    outputs = [seg.translations.get("en") for seg in translated.segments]
    assert outputs == ["first", ""]
    assert provider.calls == 3  # initial call + 2 retries


def test_glossary_applied_after_model():
    doc = _make_doc()
    glossary = {"こんにちは": "hello", "ありがとう": "thanks"}

    translated = translation.translate_document(doc, target_langs=["en"], provider="echo", glossary=glossary)

    outputs = [seg.translations.get("en") for seg in translated.segments]
    assert outputs == ["hello", "thanks"]
