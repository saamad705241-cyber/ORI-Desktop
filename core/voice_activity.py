"""Low-latency microphone voice-activity gate for barge-in.

Uses WebRTC VAD when installed. Input must be mono signed 16-bit PCM at 8/16/32/48kHz.
The fallback intentionally errs on the side of not interrupting: it uses speech-band
energy and requires multiple frames, but it is not a speaker-identity system.
"""
from __future__ import annotations

import numpy as np


class VoiceActivityGate:
    def __init__(self, aggressiveness: int = 2) -> None:
        self._vad = None
        self.available = False
        try:
            import webrtcvad
            self._vad = webrtcvad.Vad(max(0, min(3, int(aggressiveness))))
            self.available = True
        except Exception:
            self._vad = None

    def is_speech(self, pcm: bytes, sample_rate: int = 16000) -> bool:
        """True when enough 20ms chunks are classified as speech."""
        if not isinstance(pcm, (bytes, bytearray)) or len(pcm) < 640:
            return False
        if sample_rate not in (8000, 16000, 32000, 48000):
            return False
        if self._vad is not None:
            frame_size = int(sample_rate * 0.020) * 2
            results: list[bool] = []
            for offset in range(0, len(pcm) - frame_size + 1, frame_size):
                frame = bytes(pcm[offset:offset + frame_size])
                try:
                    results.append(bool(self._vad.is_speech(frame, sample_rate)))
                except Exception:
                    return False
            if not results:
                return False
            required = 2 if len(results) >= 3 else 1
            return sum(results) >= required

        # Conservative local fallback for environments where WebRTC VAD could
        # not be imported. It rejects low-energy noise and spectrally flat fans.
        try:
            x = np.frombuffer(pcm[:len(pcm) // 2 * 2], dtype=np.int16).astype(np.float32)
            if x.size < 160:
                return False
            x -= float(x.mean())
            rms = float(np.sqrt(np.mean(x * x)))
            if rms < 420:
                return False
            n = 1 << (x.size - 1).bit_length()
            spectrum = np.abs(np.fft.rfft(x * np.hanning(x.size), n=n))
            freqs = np.fft.rfftfreq(n, 1.0 / sample_rate)
            total = float(spectrum.sum()) + 1e-9
            speech = float(spectrum[(freqs >= 180) & (freqs <= 4200)].sum()) / total
            flatness = float(np.exp(np.mean(np.log(spectrum + 1e-8))) / (np.mean(spectrum) + 1e-8))
            return speech >= 0.58 and flatness < 0.58
        except Exception:
            return False
