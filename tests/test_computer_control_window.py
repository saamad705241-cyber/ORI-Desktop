from types import SimpleNamespace

from actions import computer_control as control
from actions import open_app


def _fake_window(title="Untitled - Notepad", hwnd=100, on_close=None):
    class FakeWindow:
        def __init__(self):
            self.title = title
            self._hWnd = hwnd
            self.visible = True

        def close(self):
            if on_close:
                on_close(self)

    return FakeWindow()


def test_close_window_verifies_that_the_target_disappeared(monkeypatch):
    windows = []
    target = _fake_window(on_close=lambda item: windows.remove(item))
    windows.append(target)
    monkeypatch.setattr(control, "_get_os", lambda: "windows")
    monkeypatch.setitem(
        __import__("sys").modules,
        "pygetwindow",
        SimpleNamespace(getAllWindows=lambda: list(windows)),
    )

    result = control._close_window("Notepad", timeout=0.05, poll_interval=0.001)

    assert "Verified" in result
    assert windows == []


def test_close_window_does_not_claim_success_when_save_dialog_blocks_it(monkeypatch):
    target = _fake_window()
    windows = [target]
    monkeypatch.setattr(control, "_get_os", lambda: "windows")
    monkeypatch.setitem(
        __import__("sys").modules,
        "pygetwindow",
        SimpleNamespace(getAllWindows=lambda: list(windows)),
    )

    result = control._close_window("Notepad", timeout=0.02, poll_interval=0.001)

    assert "still present" in result
    assert "unsaved-changes prompt" in result
    assert "force-terminated" in result


def test_close_window_reports_no_matching_visible_window(monkeypatch):
    monkeypatch.setattr(control, "_get_os", lambda: "windows")
    monkeypatch.setitem(
        __import__("sys").modules,
        "pygetwindow",
        SimpleNamespace(getAllWindows=lambda: []),
    )

    result = control._close_window("Notepad")

    assert "No visible window matched" in result


def test_computer_control_dispatches_close_window(monkeypatch):
    monkeypatch.setattr(control, "_close_window", lambda title: f"closed {title}")
    result = control.computer_control({
        "action": "close_window",
        "title": "Notepad",
    })
    assert result == "closed Notepad"


def test_hotkey_result_does_not_claim_resulting_app_state(monkeypatch):
    calls = []
    monkeypatch.setattr(control, "_PYAUTOGUI", True)
    monkeypatch.setattr(
        control,
        "pyautogui",
        SimpleNamespace(hotkey=lambda *keys: calls.append(keys)),
    )

    result = control._hotkey("alt", "f4")

    assert calls == [("alt", "f4")]
    assert "has not been verified" in result


def test_open_app_requires_a_visible_window_not_only_a_background_process(monkeypatch):
    monkeypatch.setattr(open_app, "_windows_running_process_ids", lambda _name: {123})
    monkeypatch.setattr(open_app, "_windows_visible_process_ids", lambda: {456})
    monkeypatch.setitem(
        __import__("sys").modules,
        "pygetwindow",
        SimpleNamespace(getAllWindows=lambda: []),
    )

    assert open_app._windows_app_visible("notepad.exe") is False


def test_open_app_verifies_matching_visible_process(monkeypatch):
    monkeypatch.setattr(open_app, "_windows_running_process_ids", lambda _name: {123})
    monkeypatch.setattr(open_app, "_windows_visible_process_ids", lambda: {123})

    assert open_app._windows_app_visible("notepad.exe") is True


def test_open_app_can_use_visible_title_fallback(monkeypatch):
    monkeypatch.setattr(open_app, "_windows_running_process_ids", lambda _name: set())
    monkeypatch.setattr(open_app, "_windows_visible_process_ids", lambda: set())
    monkeypatch.setitem(
        __import__("sys").modules,
        "pygetwindow",
        SimpleNamespace(
            getAllWindows=lambda: [
                SimpleNamespace(title="Untitled - Notepad", visible=True)
            ]
        ),
    )

    assert open_app._windows_app_visible("notepad.exe") is True


def test_youtube_empty_handler_result_is_unverified(monkeypatch):
    from actions import youtube_video

    monkeypatch.setitem(youtube_video._ACTION_MAP, "play", lambda *_args: None)

    result = youtube_video.youtube_video({"action": "play"})

    assert "outcome is unverified" in result


def test_file_processor_empty_handler_result_is_unverified(monkeypatch, tmp_path):
    from actions import file_processor

    target = tmp_path / "notes.txt"
    target.write_text("sample", encoding="utf-8")
    monkeypatch.setattr(file_processor, "_process_text_doc", lambda *_args: None)

    result = file_processor.file_processor({
        "file_path": str(target),
        "action": "summarize",
    })

    assert "outcome is unverified" in result


def test_desktop_code_without_confirmation_is_unverified():
    from actions import desktop

    result = desktop._execute_generated_code("value = 1")

    assert "outcome is unverified" in result
