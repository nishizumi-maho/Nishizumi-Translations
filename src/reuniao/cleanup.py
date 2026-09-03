"""Tidying up what the recogniser got wrong in ways a machine can spot.

Two problems, both common enough in a long meeting to be worth automating:
Whisper occasionally falls into a loop and repeats one phrase for minutes, and
it spells names and acronyms it has never seen the way they sound. Neither is
fixable by transcribing harder, and both are obvious once you look at the text.

Everything here is deliberately cautious. A transcript with a stray repetition
is a nuisance; a transcript where a correct word was "corrected" into the
wrong one is a trap, because nothing in the file says it happened.
"""
from __future__ import annotations

import re
import unicodedata
from difflib import SequenceMatcher

from .model import Segment, Utterance

#: A run has to be at least this long before it counts as a loop rather than
#: someone genuinely saying "sim, sim, sim".
LOOP_RUN = 4

#: How much of a detected loop survives. One: the header already records that
#: it happened, and a second copy only makes the transcript worse to read.
LOOP_KEEP = 1

#: Longest phrase checked for repetition, in words.
MAX_PHRASE_WORDS = 8

#: How close a word has to sound to a glossary term to be rewritten as it.
#: High on purpose: a wrong correction is worse than a missed one.
GLOSSARY_RATIO = 0.85

#: Below this length a term is only ever matched exactly (accents and case
#: aside) — at three letters almost everything is 85% similar to everything
#: else, but "okr" for "OKR" is still worth fixing and carries no risk.
GLOSSARY_FUZZY_LENGTH = 4

#: Shorter than this and a term is ignored entirely.
GLOSSARY_MIN_LENGTH = 2

_WORD_SPLIT = re.compile(r"(\W+)", flags=re.UNICODE)


# -- repetition ------------------------------------------------------------


def normalize(text: str) -> str:
    """Lowercased, unpunctuated, unaccented — for comparing, never for output."""

    folded = unicodedata.normalize("NFKD", text.lower())
    stripped = "".join(char for char in folded if not unicodedata.combining(char))
    return re.sub(r"[^\w\s]", "", stripped).strip()


def drop_repeated_segments(segments: list[Segment]) -> tuple[list[Segment], int]:
    """Trim runs of identical consecutive segments down to a couple.

    This is the shape a Whisper loop takes over silence or music: the same
    sentence, segment after segment, for as long as the silence lasts. The
    whole run is measured before anything is dropped, so three sincere
    repetitions survive and forty do not.
    """

    keys = [normalize(segment.text) for segment in segments]
    keep = [True] * len(segments)
    dropped = 0

    start = 0
    while start < len(segments):
        end = start
        while end + 1 < len(segments) and keys[end + 1] == keys[start]:
            end += 1
        run = end - start + 1
        if keys[start] and run >= LOOP_RUN:
            for index in range(start + LOOP_KEEP, end + 1):
                keep[index] = False
                dropped += 1
        start = end + 1

    return [segment for segment, wanted in zip(segments, keep) if wanted], dropped


def collapse_repeated_phrases(text: str) -> tuple[str, int]:
    """Collapse a phrase repeated back to back inside one line.

    ``obrigado obrigado obrigado obrigado`` becomes ``obrigado obrigado``.
    Longer phrases are checked too, because a loop is as often a sentence as
    it is a word.
    """

    words = text.split()
    if len(words) < LOOP_RUN:
        return text, 0

    collapsed = 0
    for size in range(1, MAX_PHRASE_WORDS + 1):
        index = 0
        result: list[str] = []
        while index < len(words):
            phrase = words[index : index + size]
            if len(phrase) < size:
                result.extend(words[index:])
                break
            repeats = 1
            while words[index + repeats * size : index + (repeats + 1) * size] == phrase:
                repeats += 1
            if repeats >= LOOP_RUN:
                result.extend(phrase * LOOP_KEEP)
                collapsed += repeats - LOOP_KEEP
                index += repeats * size
            else:
                result.extend(phrase)
                index += size
        words = result
    return " ".join(words), collapsed


# -- glossary --------------------------------------------------------------


def apply_glossary(text: str, terms: list[str]) -> tuple[str, int]:
    """Rewrite near-misses of *terms* to their proper spelling.

    Only whole words are considered, and only ones already close to a term, so
    a name the recogniser heard as "Nakagawa" can be fixed while an unrelated
    word that happens to share letters is left alone.
    """

    usable = [term.strip() for term in terms if len(term.strip()) >= GLOSSARY_MIN_LENGTH]
    if not usable or not text:
        return text, 0

    pieces = _WORD_SPLIT.split(text)
    # Even indices are words, odd ones the separators between them.
    word_slots = [index for index in range(0, len(pieces), 2) if pieces[index]]
    changes = 0

    for term in usable:
        size = len(term.split())
        if size == 1:
            changes += _replace_single(pieces, word_slots, term)
        else:
            changes += _replace_phrase(pieces, word_slots, term, size)
    return "".join(pieces), changes


def _replace_single(pieces: list[str], word_slots: list[int], term: str) -> int:
    changes = 0
    target = normalize(term)
    fuzzy = len(term) >= GLOSSARY_FUZZY_LENGTH
    for slot in word_slots:
        candidate = pieces[slot]
        if candidate == term:
            continue
        if _sounds_like(normalize(candidate), target, fuzzy=fuzzy):
            pieces[slot] = term
            changes += 1
    return changes


def _replace_phrase(pieces: list[str], word_slots: list[int], term: str, size: int) -> int:
    changes = 0
    target = normalize(term)
    fuzzy = len(term) >= GLOSSARY_FUZZY_LENGTH
    for position in range(len(word_slots) - size + 1):
        slots = word_slots[position : position + size]
        window = "".join(pieces[slots[0] : slots[-1] + 1])
        if window.strip() == term:
            continue
        if _sounds_like(normalize(window), target, fuzzy=fuzzy):
            pieces[slots[0]] = term
            for slot in slots[1:]:
                pieces[slot] = ""
                pieces[slot - 1] = ""  # the separator that preceded it
            changes += 1
    return changes


def _sounds_like(candidate: str, target: str, *, fuzzy: bool = True) -> bool:
    if not candidate or not target:
        return False
    if candidate == target:
        # Same word once accents and case are set aside — "joao" for "João",
        # "okr" for "OKR". The caller has already ruled out an exact match on
        # the raw text, so reaching here means the spelling differs.
        return True
    if not fuzzy:
        return False
    if abs(len(candidate) - len(target)) > max(2, len(target) // 3):
        return False
    return SequenceMatcher(None, candidate, target).ratio() >= GLOSSARY_RATIO


# -- the pass over a finished transcript -----------------------------------


def tidy_utterances(
    utterances: list[Utterance],
    *,
    glossary: list[str] | None = None,
    collapse_loops: bool = True,
) -> tuple[list[Utterance], int, int]:
    """Clean every turn. Returns the turns, loops collapsed, terms corrected."""

    collapsed = 0
    corrected = 0
    for item in utterances:
        text = item.text
        if collapse_loops:
            text, count = collapse_repeated_phrases(text)
            collapsed += count
        if glossary:
            text, count = apply_glossary(text, glossary)
            corrected += count
        item.text = text
    return [item for item in utterances if item.text.strip()], collapsed, corrected
