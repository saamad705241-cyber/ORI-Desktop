from actions.video_player import video_player


class _BufferingPlayer:
    def __init__(self):
        self.opened = []
        self.stopped = 0

    def video_is_open(self):
        return bool(self.opened)

    def video_is_playing(self):
        return False

    def show_video(self, source, title="", muted=True, audio_source=""):
        self.opened.append(source)

    def stop_video(self):
        self.stopped += 1
        self.opened.clear()


def test_direct_url_does_not_claim_playing_until_qt_confirms(monkeypatch):
    monkeypatch.setattr("actions.video_player._wait_for_video_playback", lambda *_a, **_k: False)
    player = _BufferingPlayer()

    result = video_player(
        {"action": "play", "source": "https://example.test/video.mp4"},
        player=player,
    )

    assert player.opened == ["https://example.test/video.mp4"]
    assert "did not confirm playback" in result
    assert "Playing that" not in result


def test_stop_distinguishes_open_but_not_yet_playing_video():
    player = _BufferingPlayer()
    player.show_video("https://example.test/video.mp4")

    result = video_player({"action": "stop"}, player=player)

    assert player.stopped == 1
    assert result == "Closed the video."
