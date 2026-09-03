"""Fixing what the recogniser got wrong — without breaking what it got right."""
from __future__ import annotations

from reuniao.cleanup import (
    apply_glossary,
    collapse_repeated_phrases,
    drop_repeated_segments,
    tidy_utterances,
)
from reuniao.model import Segment, Utterance


def _segments(*texts: str) -> list[Segment]:
    return [Segment(index, index + 1, text) for index, text in enumerate(texts)]


# -- repetition ------------------------------------------------------------


def test_a_whisper_loop_is_cut_down_to_one_copy():
    segments = _segments("bom dia", *["obrigado por assistir"] * 8, "tchau")

    kept, dropped = drop_repeated_segments(segments)

    assert [item.text for item in kept] == ["bom dia", "obrigado por assistir", "tchau"]
    assert dropped == 7


def test_three_sincere_repetitions_survive():
    # A loop is dozens of copies; someone agreeing three times is not one.
    segments = _segments("sim", "sim", "sim", "claro")

    kept, dropped = drop_repeated_segments(segments)

    assert len(kept) == 4
    assert dropped == 0


def test_punctuation_and_case_do_not_hide_a_loop():
    segments = _segments(*["Obrigado por assistir!"] * 3, "obrigado por assistir", "fim")

    kept, dropped = drop_repeated_segments(segments)

    assert dropped == 3
    assert [item.text for item in kept] == ["Obrigado por assistir!", "fim"]


def test_a_phrase_repeated_inside_one_line_is_collapsed():
    text, collapsed = collapse_repeated_phrases("vamos seguir vamos seguir vamos seguir vamos seguir ok")

    assert text == "vamos seguir ok"
    assert collapsed == 3


def test_ordinary_speech_is_left_alone():
    original = "o orçamento fecha na sexta e o relatório sai na segunda"

    text, collapsed = collapse_repeated_phrases(original)

    assert text == original
    assert collapsed == 0


# -- glossary --------------------------------------------------------------


def test_accents_and_spelling_are_repaired():
    text, changes = apply_glossary(
        "o joao nakagava fechou o projeto sakura", ["João Nakagawa", "Sakura"]
    )

    assert text == "o João Nakagawa fechou o projeto Sakura"
    assert changes == 2


def test_short_acronyms_are_fixed_only_when_they_match_exactly():
    text, changes = apply_glossary("o okr do rh está ok e a rua cheia", ["OKR", "RH"])

    # "okr" and "rh" are repaired; "ok" and "rua" are not mistaken for them.
    assert text == "o OKR do RH está ok e a rua cheia"
    assert changes == 2


def test_unrelated_words_are_never_rewritten():
    text, changes = apply_glossary("a cama estava arrumada e o carro na garagem", ["Acme", "Sakura"])

    assert changes == 0
    assert text == "a cama estava arrumada e o carro na garagem"


def test_text_already_spelled_right_is_not_counted_as_a_change():
    text, changes = apply_glossary("João Nakagawa aprovou", ["João Nakagawa"])

    assert changes == 0
    assert text == "João Nakagawa aprovou"


def test_the_tidy_pass_reports_what_it_did():
    turns = [
        Utterance(0, 4, "obrigado obrigado obrigado obrigado", None),
        Utterance(4, 8, "a acme aprovou", None),
    ]

    cleaned, collapsed, corrected = tidy_utterances(turns, glossary=["Acme"])

    assert [item.text for item in cleaned] == ["obrigado", "a Acme aprovou"]
    assert collapsed == 3
    assert corrected == 1
