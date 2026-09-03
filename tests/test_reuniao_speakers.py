"""Lining Whisper's words up with the diarizer's voices."""
from __future__ import annotations

from reuniao.diarize import renumber
from reuniao.model import Segment, SpeakerSpan, Utterance, Word
from reuniao.speakers import SpeakerTimeline, build_utterances, merge_runs


def words(text: str, start: float, step: float = 1.0) -> list[Word]:
    return [
        Word(start=start + index * step, end=start + (index + 1) * step, text=f" {word}")
        for index, word in enumerate(text.split())
    ]


def test_timeline_picks_the_voice_with_the_most_overlap():
    timeline = SpeakerTimeline([SpeakerSpan(0, 5, 0), SpeakerSpan(4.5, 10, 1)])

    assert timeline.speaker_at(1.0, 2.0) == 0
    assert timeline.speaker_at(6.0, 7.0) == 1
    # Straddling the join: the side holding more of the word wins.
    assert timeline.speaker_at(4.6, 6.0) == 1


def test_timeline_falls_back_to_the_nearest_voice_then_gives_up():
    timeline = SpeakerTimeline([SpeakerSpan(0, 2, 0)])

    assert timeline.speaker_at(2.3, 2.4) == 0  # just outside, still close
    assert timeline.speaker_at(40.0, 41.0) is None  # nowhere near anything


def test_a_segment_is_split_where_the_voice_changes():
    segment = Segment(0.0, 6.0, "um dois tres quatro cinco seis", words("um dois tres quatro cinco seis", 0.0))
    spans = [SpeakerSpan(0, 3, 0), SpeakerSpan(3, 6, 1)]

    result = build_utterances([segment], spans, merge=False)

    assert [item.speaker for item in result] == [0, 1]
    assert result[0].text == "um dois tres"
    assert result[1].text == "quatro cinco seis"


def test_a_segment_without_word_timings_goes_to_one_voice():
    segment = Segment(0.0, 4.0, "sem palavras marcadas", [])
    spans = [SpeakerSpan(0, 1, 0), SpeakerSpan(1, 4, 1)]

    result = build_utterances([segment], spans, merge=False)

    assert len(result) == 1
    assert result[0].speaker == 1  # the voice holding most of the segment


def test_unattributed_words_join_the_voice_around_them():
    segment = Segment(0.0, 3.0, "ola e tchau", words("ola e tchau", 0.0))
    # The middle word lands in a hole the diarizer heard as silence.
    spans = [SpeakerSpan(0, 1, 0), SpeakerSpan(2, 3, 0)]

    result = build_utterances([segment], spans, merge=False)

    assert len(result) == 1
    assert result[0].speaker == 0


def test_without_diarization_every_turn_is_anonymous():
    segment = Segment(0.0, 2.0, "sem interlocutores", words("sem interlocutores", 0.0))

    result = build_utterances([segment], [])

    assert [item.speaker for item in result] == [None]


def test_merge_joins_the_same_voice_and_stops_at_the_limits():
    turns = [
        Utterance(0.0, 2.0, "primeira", 0),
        Utterance(2.5, 4.0, "segunda", 0),
        Utterance(4.2, 5.0, "outra pessoa", 1),
        Utterance(30.0, 31.0, "muito depois", 1),
    ]

    merged = merge_runs(turns, merge_gap=1.0, max_block=40.0)

    assert [item.text for item in merged] == [
        "primeira segunda",
        "outra pessoa",
        "muito depois",
    ]
    assert merged[0].end == 4.0


def test_merge_respects_the_maximum_block_length():
    turns = [Utterance(0.0, 30.0, "longa", 0), Utterance(30.2, 45.0, "continua", 0)]

    merged = merge_runs(turns, merge_gap=1.0, max_block=40.0)

    assert len(merged) == 2  # joining them would run past 40 s


def test_voices_are_renumbered_in_order_of_first_speech():
    spans = [SpeakerSpan(9, 10, 8), SpeakerSpan(0, 1, 3), SpeakerSpan(4, 5, 3), SpeakerSpan(2, 3, 0)]

    result = renumber(spans)

    assert [(item.start, item.speaker) for item in result] == [(0, 0), (2, 1), (4, 0), (9, 2)]


def test_the_diarizer_never_pins_a_headcount(monkeypatch):
    """Regression guard for a measured upstream quirk.

    Handing sherpa-onnx a known number of speakers reads like the better
    option and measures worse: on a two-voice recording that auto mode splits
    correctly, asking for 2 comes back with 1. The threshold is what decides,
    so ``num_clusters`` has to stay at -1.
    """

    import sys
    import types

    captured = {}

    class Config:
        def __init__(self, **kwargs):
            captured.update(kwargs)

        def validate(self):
            return True

    class Clustering:
        def __init__(self, num_clusters, threshold):
            captured["num_clusters"] = num_clusters
            captured["threshold"] = threshold

    class Engine:
        def __init__(self, _config):
            pass

        def process(self, _samples, callback=None):
            return types.SimpleNamespace(sort_by_start_time=lambda: [])

    fake = types.SimpleNamespace(
        OfflineSpeakerDiarizationConfig=Config,
        OfflineSpeakerSegmentationModelConfig=lambda **kw: kw,
        OfflineSpeakerSegmentationPyannoteModelConfig=lambda **kw: kw,
        SpeakerEmbeddingExtractorConfig=lambda **kw: kw,
        FastClusteringConfig=Clustering,
        OfflineSpeakerDiarization=Engine,
    )
    monkeypatch.setitem(sys.modules, "sherpa_onnx", fake)

    from reuniao import diarize

    monkeypatch.setattr(diarize, "model_paths", lambda: ("seg.onnx", "emb.onnx"))

    assert diarize.diarize([0.0], threshold=0.7) == []
    assert captured["num_clusters"] == -1
    assert captured["threshold"] == 0.7


# -- consolidating the speakers the diarizer invented ----------------------


def _turn(start, end, text, speaker):
    return Utterance(start, end, text, speaker, weight=max(1, len(text.split())))


def test_splinter_speakers_are_folded_into_whoever_was_talking():
    """The shape found in a real 2h38 meeting: 36 voices, 23 of them seconds long."""

    from reuniao.speakers import consolidate_speakers

    turns = [
        _turn(0, 60, "primeira pessoa falando bastante", 0),
        _turn(61, 62, "é", 4),
        _turn(63, 120, "e continua falando", 0),
        _turn(121, 180, "agora a segunda pessoa", 1),
        _turn(181, 182, "sim", 7),
        _turn(183, 240, "e a segunda segue", 1),
    ]

    result, changed = consolidate_speakers(turns)

    assert sorted({item.speaker for item in result}) == [0, 1]
    assert changed == 2
    # The speech itself is untouched; only the name on it changed.
    assert [item.text for item in result][1] == "é"


def test_a_splinter_between_two_different_people_is_left_alone():
    from reuniao.speakers import consolidate_speakers

    turns = [
        _turn(0, 60, "a primeira pessoa fala", 0),
        _turn(61, 62, "opa", 5),
        _turn(63, 120, "e a segunda responde", 1),
    ]

    result, changed = consolidate_speakers(turns)

    # Handing it to either side would be a guess, so it keeps its own label.
    assert changed == 0
    assert len({item.speaker for item in result}) == 3


def test_a_short_opening_line_is_not_stolen_by_whoever_speaks_next():
    from reuniao.speakers import consolidate_speakers

    turns = [_turn(0, 1.2, "bom dia", 0), _turn(2, 90, "então vamos à pauta de hoje", 1)]

    result, changed = consolidate_speakers(turns)

    assert changed == 0
    assert [item.speaker for item in result] == [0, 1]


def test_a_real_speaker_is_never_folded_away_however_briefly_they_speak():
    from reuniao.speakers import consolidate_speakers

    # Twenty seconds is short for a meeting but far from a splinter.
    turns = [
        _turn(0, 60, "a primeira pessoa", 0),
        _turn(61, 81, "uma intervenção curta mas real de vinte segundos", 2),
        _turn(82, 140, "e a primeira retoma", 0),
    ]

    result, changed = consolidate_speakers(turns)

    assert changed == 0
    assert sorted({item.speaker for item in result}) == [0, 1]  # renumbered, not merged


def test_numbering_closes_the_gaps_left_behind():
    from reuniao.speakers import renumber_speakers

    turns = [_turn(0, 1, "a", 3), _turn(1, 2, "b", 9), _turn(2, 3, "c", 3)]

    result = renumber_speakers(turns)

    assert [item.speaker for item in result] == [0, 1, 0]
