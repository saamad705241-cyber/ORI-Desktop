from actions.desktop import _execute_generated_code
from actions import youtube_video


def test_desktop_code_without_output_is_not_reported_as_done():
    result = _execute_generated_code("value = 1")

    assert "unverified" in result.lower()
    assert "do not report" in result.lower()


def test_youtube_handler_without_confirmation_is_not_reported_as_done(monkeypatch):
    monkeypatch.setitem(youtube_video._ACTION_MAP, "play", lambda _params, _player: None)

    result = youtube_video.youtube_video({"action": "play"}, player=None)

    assert "unverified" in result.lower()
    assert "do not report" in result.lower()


def test_youtube_handler_empty_string_is_not_reported_as_done(monkeypatch):
    monkeypatch.setitem(youtube_video._ACTION_MAP, "summarize", lambda _params, _player, _speak: "  ")

    result = youtube_video.youtube_video(
        {"action": "summarize"}, player=None, speak=lambda _text: None
    )

    assert "unverified" in result.lower()
    assert "do not report" in result.lower()
