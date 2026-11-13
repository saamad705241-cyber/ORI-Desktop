from core.media_sync import audio_sync_action


def test_small_split_stream_drift_does_not_seek_or_change_rate():
    assert audio_sync_action(90) == (1.0, False)
    assert audio_sync_action(-140) == (1.0, False)


def test_medium_drift_uses_small_playback_rate_correction():
    assert audio_sync_action(450) == (0.98, False)
    assert audio_sync_action(-450) == (1.02, False)


def test_large_drift_requests_a_hard_seek():
    assert audio_sync_action(1200) == (1.0, True)
    assert audio_sync_action(-1200) == (1.0, True)
