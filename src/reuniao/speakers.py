"""Deciding who said each line.

Whisper says *when* each word was spoken; the diarizer says *who* was speaking
at each moment. This module lines the two up, splits a Whisper segment when
the voice changes inside it, and then glues consecutive lines from the same
person back into readable turns.
"""
from __future__ import annotations

from bisect import bisect_left

from .model import Segment, SpeakerSpan, Utterance, Word

#: How far a word may sit from any diarized span and still be attributed to it.
NEAREST_TOLERANCE = 0.75


class SpeakerTimeline:
    """Fast "who was speaking at this moment?" lookups over sorted spans."""

    def __init__(self, spans: list[SpeakerSpan]):
        self.spans = sorted(spans, key=lambda item: (item.start, item.end))
        self._starts = [item.start for item in self.spans]

    def __bool__(self) -> bool:
        return bool(self.spans)

    @property
    def speaker_count(self) -> int:
        return len({item.speaker for item in self.spans})

    def speaker_at(self, start: float, end: float) -> int | None:
        """The voice overlapping ``[start, end]`` most, or the nearest one.

        ``None`` means no span is close enough to claim it — the word landed in
        a stretch the diarizer heard as silence or crosstalk.
        """

        if not self.spans:
            return None

        # Spans are sorted, so only the handful around this window can match.
        first = max(0, bisect_left(self._starts, start) - 2)
        best_speaker: int | None = None
        best_overlap = 0.0
        nearest_speaker: int | None = None
        nearest_gap = float("inf")

        for span in self.spans[first:]:
            if span.start > end + NEAREST_TOLERANCE:
                break
            overlap = min(end, span.end) - max(start, span.start)
            if overlap > best_overlap:
                best_overlap, best_speaker = overlap, span.speaker
            if overlap <= 0:
                gap = span.start - end if span.start > end else start - span.end
                if 0 <= gap < nearest_gap:
                    nearest_gap, nearest_speaker = gap, span.speaker

        if best_speaker is not None and best_overlap > 0:
            return best_speaker
        if nearest_speaker is not None and nearest_gap <= NEAREST_TOLERANCE:
            return nearest_speaker
        return None


def build_utterances(
    segments: list[Segment],
    spans: list[SpeakerSpan] | None = None,
    *,
    merge: bool = True,
    merge_gap: float = 1.2,
    max_block: float = 40.0,
) -> list[Utterance]:
    """Turn Whisper segments plus diarization into the transcript's turns.

    With ``merge`` off the turns stay as short as Whisper and the diarizer cut
    them, which is what the subtitle exports want.
    """

    timeline = SpeakerTimeline(spans or [])
    pieces: list[Utterance] = []
    for segment in segments:
        pieces.extend(_split_segment(segment, timeline))
    if not merge:
        return [item for item in pieces if item.text]
    return merge_runs(pieces, merge_gap=merge_gap, max_block=max_block)


def _split_segment(segment: Segment, timeline: SpeakerTimeline) -> list[Utterance]:
    """One segment becomes several turns when more than one person speaks in it."""

    text = segment.text.strip()
    if not text:
        return []
    if not timeline:
        return [Utterance(start=segment.start, end=segment.end, text=text, speaker=None)]

    words = [word for word in segment.words if word.text.strip()]
    if not words:
        # No word timings: the whole segment goes to whoever dominates it.
        speaker = timeline.speaker_at(segment.start, segment.end)
        return [Utterance(start=segment.start, end=segment.end, text=text, speaker=speaker)]

    labelled = [(word, timeline.speaker_at(word.start, word.end)) for word in words]
    _fill_gaps(labelled)

    result: list[Utterance] = []
    run: list[Word] = []
    current: int | None = labelled[0][1]
    for word, speaker in labelled:
        if speaker != current and run:
            result.append(_utterance_from(run, current))
            run = []
        current = speaker
        run.append(word)
    if run:
        result.append(_utterance_from(run, current))
    return [item for item in result if item.text]


def _fill_gaps(labelled: list[tuple[Word, int | None]]) -> None:
    """Give unattributed words the voice around them, in place.

    A single "é" landing between two spans should not open a nameless turn; it
    belongs to whoever was talking on either side of it.
    """

    known = [index for index, (_word, speaker) in enumerate(labelled) if speaker is not None]
    if not known:
        return
    for index, (word, speaker) in enumerate(labelled):
        if speaker is not None:
            continue
        before = [pos for pos in known if pos < index]
        after = [pos for pos in known if pos > index]
        source = before[-1] if before else after[0]
        labelled[index] = (word, labelled[source][1])


def _utterance_from(words: list[Word], speaker: int | None) -> Utterance:
    text = "".join(word.text for word in words).strip()
    return Utterance(start=words[0].start, end=words[-1].end, text=text, speaker=speaker)


def merge_runs(
    utterances: list[Utterance], *, merge_gap: float = 1.2, max_block: float = 40.0
) -> list[Utterance]:
    """Join neighbouring turns from the same person into one readable block."""

    merged: list[Utterance] = []
    for item in utterances:
        if not item.text:
            continue
        if not merged:
            merged.append(Utterance(item.start, item.end, item.text, item.speaker))
            continue

        previous = merged[-1]
        same_person = previous.speaker == item.speaker
        gap = item.start - previous.end
        length = item.end - previous.start
        if same_person and gap <= merge_gap and length <= max_block:
            previous.end = item.end
            previous.text = f"{previous.text} {item.text}".strip()
        else:
            merged.append(Utterance(item.start, item.end, item.text, item.speaker))
    return merged
