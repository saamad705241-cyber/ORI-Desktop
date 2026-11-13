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


def test_file_processor_none_result_is_not_reported_as_success(monkeypatch, tmp_path):
    from actions import file_processor

    sample = tmp_path / "sample.txt"
    sample.write_text("sample content", encoding="utf-8")
    monkeypatch.setattr(file_processor, "_detect_type", lambda _path: "text")
    monkeypatch.setattr(file_processor, "_process_text_doc", lambda *_args: None)

    result = file_processor.file_processor(
        {"file_path": str(sample), "action": "extract"}
    )

    assert "unverified" in result.lower()
    assert "do not report" in result.lower()


def test_computer_settings_dispatch_does_not_claim_completion(monkeypatch):
    from actions import computer_settings

    monkeypatch.setattr(computer_settings, "_PYAUTOGUI", True)
    monkeypatch.setitem(computer_settings.ACTION_MAP, "show_desktop", lambda: None)

    result = computer_settings.computer_settings({"action": "show_desktop"})

    assert "unverified" in result.lower()
    assert "do not report" in result.lower() or "not verified" in result.lower()


def test_blind_messaging_does_not_claim_delivery(monkeypatch):
    from types import SimpleNamespace
    from actions import send_message

    monkeypatch.setattr(send_message, "_open_app", lambda _app: True)
    monkeypatch.setattr(send_message, "_search_in_app", lambda _receiver: None)
    monkeypatch.setattr(send_message, "_paste_text", lambda _text: None)
    monkeypatch.setattr(send_message.time, "sleep", lambda _seconds: None)
    monkeypatch.setattr(send_message, "pyautogui", SimpleNamespace(press=lambda _key: None))

    result = send_message._desktop_send("Telegram", "Test User", "Hello")

    assert "delivery were not verified" in result.lower()
    assert "do not say the message was sent" in result.lower()



def test_computer_settings_close_app_uses_verified_window_close(monkeypatch):
    import sys
    from types import ModuleType, SimpleNamespace
    from actions import computer_settings, computer_control

    fake_window = SimpleNamespace(title="Untitled - Notepad")
    fake_pygetwindow = ModuleType("pygetwindow")
    fake_pygetwindow.getActiveWindow = lambda: fake_window
    monkeypatch.setitem(sys.modules, "pygetwindow", fake_pygetwindow)
    monkeypatch.setattr(computer_settings, "_OS", "Windows")
    monkeypatch.setattr(
        computer_control,
        "_close_window",
        lambda title: f"Closed '{title}' and verified the process has no visible windows.",
    )

    result = computer_settings.close_app()

    assert "verified" in result.lower()
    assert "notepad" in result.lower()


def test_computer_settings_close_window_shortcut_is_not_a_verified_close(monkeypatch):
    from actions import computer_settings
    from types import SimpleNamespace

    monkeypatch.setattr(computer_settings, "_PYAUTOGUI", True)
    monkeypatch.setattr(computer_settings, "_OS", "Windows")
    monkeypatch.setattr(
        computer_settings,
        "pyautogui",
        SimpleNamespace(hotkey=lambda *_keys: None),
        raising=False,
    )

    result = computer_settings.computer_settings({"action": "close_window"})

    assert "unverified" in result.lower()
