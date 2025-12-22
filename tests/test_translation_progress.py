from jp2subs.models import MasterDocument, Meta, Segment
from jp2subs.progress import stage_percent
from jp2subs import translation


class _FakeProvider(translation.TranslationProvider):
    def translate_block(
        self,
        lines,
        source_lang,
        target_lang,
        glossary=None,
        *,
        register_subprocess=None,
        check_cancelled=None,
    ):
        return [f"{target_lang}:{line}" for line in lines]


def test_translate_document_emits_block_progress(monkeypatch):
    doc = MasterDocument(
        meta=Meta(source="test"),
        segments=[Segment(id=i, start=0, end=1, ja_raw=f"seg{i}") for i in range(5)],
    )

    events = []

    monkeypatch.setattr(translation, "_provider_from_name", lambda name: _FakeProvider())

    translation.translate_document(
        doc,
        target_langs=["en"],
        block_size=2,
        on_progress=lambda evt: events.append(evt),
    )

    # 3 blocks for 5 segments + final completion event
    assert len(events) == 4
    assert events[0].percent == stage_percent("Translate", 1 / 3)
    assert "Block 1/3" in events[0].detail
    assert events[-1].percent == stage_percent("Translate", 1)
    assert events[-1].message.startswith("Translation complete")
