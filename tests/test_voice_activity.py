import sys
import types

from core.voice_activity import VoiceActivityGate


class FakeVad:
    def __init__(self, mode):
        self.mode = mode
        self.calls = 0

    def is_speech(self, frame, sample_rate):
        self.calls += 1
        assert sample_rate == 16000
        return self.calls in (1, 2)


def test_webrtc_vad_requires_multiple_voiced_frames(monkeypatch):
    fake_module = types.SimpleNamespace(Vad=FakeVad)
    monkeypatch.setitem(sys.modules, "webrtcvad", fake_module)
    gate = VoiceActivityGate(2)
    assert gate.available is True
    assert gate.is_speech(b"\x00\x00" * 1024, 16000) is True


def test_short_or_invalid_audio_never_counts_as_speech(monkeypatch):
    fake_module = types.SimpleNamespace(Vad=FakeVad)
    monkeypatch.setitem(sys.modules, "webrtcvad", fake_module)
    gate = VoiceActivityGate(2)
    assert gate.is_speech(b"\x00" * 100, 16000) is False
    assert gate.is_speech(b"\x00" * 2048, 22050) is False


def test_fallback_rejects_silence(monkeypatch):
    monkeypatch.setitem(sys.modules, "webrtcvad", None)
    gate = VoiceActivityGate(2)
    assert gate.available is False
    assert gate.is_speech(b"\x00\x00" * 1024, 16000) is False
