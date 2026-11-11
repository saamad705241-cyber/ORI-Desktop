import math
import unittest
import numpy as np
from core.audio_spectrum import pcm_spectrum, pcm_level


class AudioSpectrumTests(unittest.TestCase):
    def make_tone(self, frequency, sample_rate=16000, size=2048, amplitude=12000):
        t = np.arange(size, dtype=np.float32) / sample_rate
        return (np.sin(2 * math.pi * frequency * t) * amplitude).astype(np.int16)

    def test_silence_returns_flat_spectrum(self):
        self.assertEqual(pcm_spectrum(np.zeros(2048, dtype=np.int16), 16000), [0.0] * 64)
        self.assertEqual(pcm_level(np.zeros(2048, dtype=np.int16)), 0.0)

    def test_distinct_frequencies_peak_in_distinct_bands(self):
        bass = pcm_spectrum(self.make_tone(110), 16000)
        treble = pcm_spectrum(self.make_tone(5200), 16000)
        self.assertEqual(len(bass), 64)
        self.assertEqual(len(treble), 64)
        self.assertNotEqual(max(range(64), key=bass.__getitem__), max(range(64), key=treble.__getitem__))
        self.assertGreater(max(bass), 0.9)
        self.assertGreater(max(treble), 0.9)

    def test_invalid_input_fails_soft(self):
        self.assertEqual(pcm_spectrum([], 16000), [0.0] * 64)

if __name__ == "__main__":
    unittest.main()
