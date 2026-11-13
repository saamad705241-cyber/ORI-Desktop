from actions import video_player


class _SpeechCapture:
    def __init__(self):
        self.messages = []

    def request_say(self, message):
        self.messages.append(message)


def test_youtube_fallback_does_not_claim_browser_open_when_browser_returns_false(monkeypatch):
    player = _SpeechCapture()
    monkeypatch.setattr(video_player, "_resolve_youtube", lambda _source: ("", "", "", "resolution failed"))
    monkeypatch.setattr(video_player, "_still_wanted", lambda _token: True)
    monkeypatch.setattr(video_player, "_search_page", lambda _source: "https://example.test/search")
    monkeypatch.setattr(video_player.webbrowser, "open", lambda _url: False)

    video_player._play_youtube(player, "example video", 1)

    assert len(player.messages) == 1
    assert "browser also did not confirm that it opened" in player.messages[0]
    assert "opened in the browser instead" not in player.messages[0]


def test_youtube_fallback_reports_browser_request_only_when_browser_returns_true(monkeypatch):
    player = _SpeechCapture()
    monkeypatch.setattr(video_player, "_resolve_youtube", lambda _source: ("", "", "", "resolution failed"))
    monkeypatch.setattr(video_player, "_still_wanted", lambda _token: True)
    monkeypatch.setattr(video_player, "_search_page", lambda _source: "https://example.test/search")
    monkeypatch.setattr(video_player.webbrowser, "open", lambda _url: True)

    video_player._play_youtube(player, "example video", 1)

    assert "browser accepted the fallback page request" in player.messages[0]
