import pytest

from jp2subs import translation


def test_translate_document_rejected():
    doc = None

    with pytest.raises(RuntimeError):
        translation.translate_document(doc, target_langs=["en"])  # type: ignore[arg-type]
