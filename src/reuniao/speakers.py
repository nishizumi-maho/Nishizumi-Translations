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

#: A voice holding less than this share of the speech, and less than
#: :data:`TINY_SPEAKER_SECONDS` in total, is treated as a splinter of a real
#: speaker rather than a person. Measured on a real 2h38 meeting: 23 of the 36
#: "speakers" found held two minutes between them, and 41 of their turns sat
#: alone between two turns of the same other person.
TINY_SPEAKER_SHARE = 0.01
TINY_SPEAKER_SECONDS = 15.0

#: An aside this short, surrounded by one other voice, is read as belonging to
#: that voice: too little sound to fingerprint, and backchannel either way.
ISLAND_SECONDS = 1.5
ISLAND_WORDS = 3


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
        return [
            Utterance(
                start=segment.start,
                end=segment.end,
                text=text,
                speaker=None,
                confidence=segment.confidence,
                weight=max(1, len(text.split())),
            )
        ]

    words = [word for word in segment.words if word.text.strip()]
    if not words:
        # No word timings: the whole segment goes to whoever dominates it.
        speaker = timeline.speaker_at(segment.start, segment.end)
        return [
            Utterance(
                start=segment.start,
                end=segment.end,
                text=text,
                speaker=speaker,
                confidence=segment.confidence,
                weight=max(1, len(text.split())),
            )
        ]

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
    confidence = sum(word.confidence for word in words) / len(words)
    return Utterance(
        start=words[0].start,
        end=words[-1].end,
        text=text,
        speaker=speaker,
        confidence=confidence,
        weight=len(words),
    )


def merge_runs(
    utterances: list[Utterance], *, merge_gap: float = 1.2, max_block: float = 40.0
) -> list[Utterance]:
    """Join neighbouring turns from the same person into one readable block."""

    merged: list[Utterance] = []
    for item in utterances:
        if not item.text:
            continue
        if not merged:
            merged.append(
                Utterance(item.start, item.end, item.text, item.speaker, item.confidence, item.weight)
            )
            continue

        previous = merged[-1]
        same_person = previous.speaker == item.speaker
        # Doubtful speech stays in its own turn. Merged into a confident
        # paragraph its low confidence would average away, and the mark that
        # should point at one mumbled sentence would either vanish or smear
        # over forty seconds of perfectly good transcript.
        same_certainty = previous.uncertain == item.uncertain
        gap = item.start - previous.end
        length = item.end - previous.start
        if same_person and same_certainty and gap <= merge_gap and length <= max_block:
            previous.end = item.end
            previous.text = f"{previous.text} {item.text}".strip()
            # Weighted by word count: averaging two averages would let a
            # three-word aside outvote a paragraph.
            total = previous.weight + item.weight
            previous.confidence = (
                previous.confidence * previous.weight + item.confidence * item.weight
            ) / max(1, total)
            previous.weight = total
        else:
            merged.append(
                Utterance(item.start, item.end, item.text, item.speaker, item.confidence, item.weight)
            )
    return merged


def consolidate_speakers(
    turns: list[Utterance],
    *,
    tiny_share: float = TINY_SPEAKER_SHARE,
    tiny_seconds: float = TINY_SPEAKER_SECONDS,
) -> tuple[list[Utterance], int]:
    """Fold away the speakers the diarizer invented.

    Clustering short, noisy speech invents people: a cough, an overlap or one
    word from across the room becomes its own voice. They are recognisable
    without hearing anything, because a person in a meeting talks for minutes
    and a splinter talks for seconds.

    Nothing is deleted — the speech keeps its place and its timing, and only
    the name on it changes, to whoever was talking around it.
    """

    if not turns:
        return turns, 0

    seconds: dict[int | None, float] = {}
    for item in turns:
        if item.speaker is not None:
            seconds[item.speaker] = seconds.get(item.speaker, 0.0) + item.duration
    total = sum(seconds.values())
    if not total:
        return turns, 0

    splinters = {
        speaker
        for speaker, value in seconds.items()
        if value < tiny_seconds and (value / total) < tiny_share
    }

    changed = 0
    for index, item in enumerate(turns):
        if item.speaker is None:
            continue
        is_splinter = item.speaker in splinters
        is_island = item.duration <= ISLAND_SECONDS and len(item.text.split()) <= ISLAND_WORDS
        if not is_splinter and not is_island:
            continue
        # A splinter carries its own evidence — this "speaker" barely exists —
        # so one neighbour is enough to place it. A merely short turn does not:
        # the first thing said in a meeting is often three words, and with only
        # the turn after it to go on, absorbing it would just hand it to
        # whoever spoke next.
        host = _surrounding_speaker(turns, index, splinters, one_sided=is_splinter)
        if host is not None and host != item.speaker:
            item.speaker = host
            changed += 1

    return renumber_speakers(turns), changed


def _surrounding_speaker(
    turns: list[Utterance], index: int, splinters: set[int], *, one_sided: bool
) -> int | None:
    """Who was talking either side of ``turns[index]``.

    Both sides have to agree: a turn between two different people is a real
    handover, and guessing which of them it belongs to would be worse than
    leaving it alone. With ``one_sided`` a single neighbour will do, for turns
    already known to belong to nobody.
    """

    before = _neighbour(turns, index, -1, splinters)
    after = _neighbour(turns, index, 1, splinters)
    if before is not None and after is not None:
        return before if before == after else None
    if not one_sided:
        return None
    return before if before is not None else after


def _neighbour(turns: list[Utterance], index: int, step: int, splinters: set[int]) -> int | None:
    position = index + step
    while 0 <= position < len(turns):
        speaker = turns[position].speaker
        if speaker is not None and speaker not in splinters:
            return speaker
        position += step
    return None


def renumber_speakers(turns: list[Utterance]) -> list[Utterance]:
    """Relabel voices 0, 1, 2... in order of first speech, with no gaps.

    Absorbing a splinter leaves a hole in the numbering, and a transcript that
    jumps from Interlocutor 3 to Interlocutor 9 reads like someone is missing.
    """

    mapping: dict[int, int] = {}
    for item in turns:
        if item.speaker is None:
            continue
        if item.speaker not in mapping:
            mapping[item.speaker] = len(mapping)
    for item in turns:
        if item.speaker is not None:
            item.speaker = mapping[item.speaker]
    return turns


def overlap_regions(spans: list[SpeakerSpan]) -> list[tuple[float, float]]:
    """Stretches where more than one voice is active at once.

    A sweep over the starts and ends, counting how many *distinct* voices are
    open. Two spans of the same speaker touching is not crosstalk; two people
    talking over each other is.
    """

    events: list[tuple[float, int, int]] = []
    for span in spans:
        events.append((span.start, 1, span.speaker))
        events.append((span.end, -1, span.speaker))
    events.sort(key=lambda item: (item[0], -item[1]))

    active: dict[int, int] = {}
    regions: list[tuple[float, float]] = []
    opened: float | None = None

    for moment, delta, speaker in events:
        before = len(active)
        active[speaker] = active.get(speaker, 0) + delta
        if active[speaker] <= 0:
            active.pop(speaker, None)
        after = len(active)
        if before < 2 <= after:
            opened = moment
        elif before >= 2 > after and opened is not None:
            if moment > opened:
                regions.append((opened, moment))
            opened = None
    return regions


def mark_overlaps(
    turns: list[Utterance], spans: list[SpeakerSpan], *, min_share: float = 0.2
) -> int:
    """Flag turns spoken while somebody else was talking. Returns how many.

    Only a turn substantially inside crosstalk is flagged: a quarter-second
    brush with the end of someone else's sentence is normal conversation, not
    a passage to distrust.
    """

    regions = overlap_regions(spans)
    if not regions:
        return 0

    flagged = 0
    for turn in turns:
        length = turn.end - turn.start
        if length <= 0:
            continue
        covered = sum(
            max(0.0, min(turn.end, end) - max(turn.start, start)) for start, end in regions
        )
        if covered / length >= min_share:
            turn.overlapped = True
            flagged += 1
    return flagged
