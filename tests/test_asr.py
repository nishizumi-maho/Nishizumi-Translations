from __future__ import annotations

import sys
import types

from jp2subs import asr


def _install_fake_whisper(monkeypatch, attempts, fail_on_cuda: bool = False):
    class FakeSegment:
        def __init__(self):
            self.start = 0
            self.end = 1
            self.text = "hello"
            self.words = []

    class FakeModel:
        def __init__(self, model_size: str, device: str = "cpu", **_: object):
            if device is None:
                raise TypeError("device cannot be None")
            attempts.append(device)
            if fail_on_cuda and device == "cuda":
                raise RuntimeError("no cuda available")
            self._model_size = model_size

        def transcribe(self, *_: object, **__: object):
            return [FakeSegment()], {"language": "ja"}

    monkeypatch.setitem(sys.modules, "faster_whisper", types.SimpleNamespace(WhisperModel=FakeModel))


def test_transcribe_auto_fallbacks_to_cpu(monkeypatch, tmp_path):
    attempts: list[str] = []
    _install_fake_whisper(monkeypatch, attempts, fail_on_cuda=True)
    monkeypatch.setattr(asr, "_probe_duration", lambda _path: 1.0)

    audio_path = tmp_path / "audio.wav"
    audio_path.write_text("data", encoding="utf-8")

    doc = asr.transcribe_audio(audio_path, device=None)

    assert attempts == ["cuda", "cpu"]
    assert doc.segments[0].ja_raw == "hello"


def test_transcribe_cpu_device(monkeypatch, tmp_path):
    attempts: list[str] = []
    _install_fake_whisper(monkeypatch, attempts)
    monkeypatch.setattr(asr, "_probe_duration", lambda _path: 1.0)

    audio_path = tmp_path / "audio.wav"
    audio_path.write_text("data", encoding="utf-8")

    asr.transcribe_audio(audio_path, device="cpu")

    assert attempts == ["cpu"]
