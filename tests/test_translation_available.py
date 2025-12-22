from jp2subs import config, translation


def test_translation_unavailable():
    ok, reason = translation.is_translation_available(config.AppConfig())

    assert ok is False
    assert "removed" in reason.lower()
