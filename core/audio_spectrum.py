"""Realtime logarithmic audio spectrum helpers for ORI's audio HUD.

The output is a normalized set of frequency-band energies derived from PCM.
It intentionally contains no visual animation or GUI code so it can be tested
without starting the desktop application.
"""
from __future__ import annotations

import numpy as np

_LEVEL_FLOOR = 60.0
_LEVEL_FULL = 2600.0


def pcm_level(samples) -> float:
    """Map int16 PCM to 0..1 loudness; quiet hardware noise returns zero."""
    try:
        x = np.asarray(samples, dtype=np.float32).reshape(-1)
        if not x.size:
            return 0.0
        rms = float(np.sqrt(np.mean(x * x)))
        if not np.isfinite(rms) or rms <= _LEVEL_FLOOR:
            return 0.0
        return max(0.0, min(1.0, (rms - _LEVEL_FLOOR) / (_LEVEL_FULL - _LEVEL_FLOOR)))
    except Exception:
        return 0.0


def pcm_spectrum(samples, sample_rate: int, bands: int = 64) -> list[float]:
    """Calculate log-spaced bass/mid/treble energy from actual PCM.

    Every returned value is 0..1. Silence and noise-floor blocks return all
    zeros, so a visualizer can settle to a flat line without fake movement.
    """
    count = max(8, int(bands))
    zeros = [0.0] * count
    try:
        x = np.asarray(samples, dtype=np.float32).reshape(-1)
        if x.size < 64:
            return zeros
        x = x - float(np.mean(x))
        rms = float(np.sqrt(np.mean(x * x)))
        if not np.isfinite(rms) or rms <= _LEVEL_FLOOR:
            return zeros
        window = np.hanning(x.size).astype(np.float32, copy=False)
        spectrum = np.abs(np.fft.rfft(x * window)).astype(np.float32, copy=False)
        frequencies = np.fft.rfftfreq(x.size, d=1.0 / max(1, int(sample_rate)))
        low_hz = 65.0
        high_hz = max(low_hz * 1.2, min(11000.0, float(sample_rate) * 0.49))
        edges = np.geomspace(low_hz, high_hz, count + 1)
        energies: list[float] = []
        for i in range(count):
            in_band = (frequencies >= edges[i]) & (frequencies < edges[i + 1])
            if not np.any(in_band):
                energies.append(0.0)
                continue
            vals = spectrum[in_band]
            energies.append(float(np.sqrt(np.mean(vals * vals))))
        peak = max(energies, default=0.0)
        if peak <= 1e-6:
            return zeros
        loudness = pcm_level(x)
        result = []
        for energy in energies:
            relative = max(0.0, min(1.0, energy / peak))
            result.append(max(0.0, min(1.0, loudness * (relative ** 0.62))))
        return result
    except Exception:
        return zeros
