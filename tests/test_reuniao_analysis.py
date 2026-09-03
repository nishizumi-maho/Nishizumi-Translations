"""Measuring a recording, and turning the numbers into advice."""
from __future__ import annotations

from reuniao.analysis import Measurement, _parse, advise

#: What FFmpeg actually prints, trimmed to the parts that are read.
FFMPEG_REPORT = """
[Parsed_astats_0 @ 0x55] Channel: 1
[Parsed_astats_0 @ 0x55] Peak count: 812
[Parsed_astats_0 @ 0x55] Number of samples: 256000
[Parsed_loudnorm_1 @ 0x66]
{
	"input_i" : "-31.42",
	"input_tp" : "-0.05",
	"input_lra" : "18.30",
	"input_thresh" : "-41.68",
	"normalization_type" : "dynamic"
}
"""


def test_the_numbers_are_read_out_of_ffmpeg_output():
    found = _parse(FFMPEG_REPORT)

    assert found.loudness == -31.42
    assert found.range_lu == 18.30
    assert found.peak_dbtp == -0.05
    assert found.peak_count == 812
    assert found.samples == 256000


def test_output_without_a_measurement_does_not_invent_one():
    found = _parse("nada de útil aqui")

    assert found.loudness is None
    assert found.range_lu is None


def test_silence_is_reported_as_unmeasured_rather_than_as_a_number():
    found = _parse('{"input_i": "-inf", "input_lra": "0.00", "input_tp": "-inf"}')

    assert found.loudness is None
    assert found.peak_dbtp is None


def test_a_wide_range_recommends_the_dynamic_pass():
    """The far-microphone case the filter exists for."""

    advice = advise(Measurement(loudness=-26.0, range_lu=22.7, peak_dbtp=-3.0))

    assert advice.recommend_dynamic is True
    assert any("NIVELAMENTO DINÂMICO" in line for line in advice.lines)


def test_an_even_recording_is_left_alone():
    advice = advise(Measurement(loudness=-20.0, range_lu=6.5, peak_dbtp=-1.0))

    assert advice.recommend_dynamic is False
    assert any("volumes parecidos" in line for line in advice.lines)


def test_a_quiet_recording_is_called_out():
    advice = advise(Measurement(loudness=-34.0, range_lu=5.0, peak_dbtp=-9.0))

    assert any("baixa" in line for line in advice.lines)
    assert advice.recommend_level is True


def test_clipping_is_reported_as_unrecoverable():
    advice = advise(Measurement(loudness=-12.0, range_lu=5.0, peak_dbtp=0.0, peak_count=9000, samples=100000))

    assert any("ESTOURADA" in line for line in advice.lines)
    # Saying it can be fixed would be a lie: the samples were never recorded.
    assert any("Nada recupera" in line for line in advice.lines)


def test_an_unmeasurable_file_still_gets_an_answer():
    advice = advise(Measurement())

    assert advice.lines
    assert advice.recommend_level is True
    assert advice.recommend_dynamic is False


def test_clipping_is_judged_by_peaks_as_well_as_by_true_peak():
    quiet_but_clipped = Measurement(loudness=-20.0, peak_dbtp=-2.0, peak_count=500, samples=100000)

    assert quiet_but_clipped.clipped is True
    assert Measurement(loudness=-20.0, peak_dbtp=-2.0, peak_count=1, samples=100000).clipped is False
