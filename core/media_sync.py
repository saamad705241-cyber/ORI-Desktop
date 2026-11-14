"""Pure playback-sync policy shared by the HUD and its regression tests."""
from __future__ import annotations


def audio_sync_action(
    audio_minus_video_ms: float,
    *,
    soft_limit_ms: float = 150.0,
    hard_limit_ms: float = 900.0,
) -> tuple[float, bool]:
    """Return (audio playback rate, should_hard_seek).

    Small drift is corrected gently with a tiny rate adjustment. Large drift
    requests one explicit seek; the UI applies a cooldown so it cannot seek
    every second and repeatedly interrupt the soundtrack.
    """
    drift = float(audio_minus_video_ms)
    magnitude = abs(drift)
    if magnitude <= max(0.0, soft_limit_ms):
        return 1.0, False
    if magnitude >= max(soft_limit_ms + 1.0, hard_limit_ms):
        return 1.0, True
    return (0.995 if drift > 0 else 1.005), False
