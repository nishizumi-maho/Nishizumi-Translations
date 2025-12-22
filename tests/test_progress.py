from jp2subs.progress import stage_percent, transcribe_time_percent


def test_transcribe_time_percent_clamps_and_scales():
    assert transcribe_time_percent(0, 100) == stage_percent("Transcribe", 0)
    assert transcribe_time_percent(50, 100) == stage_percent("Transcribe", 0.5)
    # Overrun clamps to 100% of stage
    assert transcribe_time_percent(150, 100) == stage_percent("Transcribe", 1)
    # Zero duration falls back to start of range
    assert transcribe_time_percent(10, 0) == stage_percent("Transcribe", 0)
