from types import ModuleType, SimpleNamespace
import sys

from actions import computer_control


def _fake_win32(monkeypatch, windows, close_behavior="close"):
    gui = ModuleType("win32gui")
    constants = ModuleType("win32con")
    constants.WM_CLOSE = 0x0010

    def enum_windows(callback, extra):
        for handle in list(windows):
            callback(handle, extra)

    def get_window_thread_process_id(handle):
        return (1, windows[handle]["pid"])

    def post_message(handle, message, _wparam, _lparam):
        assert message == constants.WM_CLOSE
        if close_behavior == "close":
            windows.pop(handle, None)
        elif close_behavior == "save_dialog":
            windows.pop(handle, None)
            windows[2] = {
                "pid": 77,
                "title": "Save As",
                "class": "#32770",
            }
        return True

    gui.EnumWindows = enum_windows
    gui.IsWindowVisible = lambda handle: handle in windows
    gui.GetWindowText = lambda handle: windows[handle]["title"]
    gui.GetWindowThreadProcessId = get_window_thread_process_id
    gui.GetClassName = lambda handle: windows[handle]["class"]
    gui.PostMessage = post_message
    monkeypatch.setitem(sys.modules, "win32gui", gui)
    monkeypatch.setitem(sys.modules, "win32con", constants)
    monkeypatch.setattr(computer_control.platform, "system", lambda: "Windows")


def test_close_window_uses_graceful_close_and_verifies_disappearance(monkeypatch):
    windows = {
        1: {"pid": 77, "title": "Untitled - Notepad", "class": "Notepad"}
    }
    _fake_win32(monkeypatch, windows)

    result = computer_control._close_window("Notepad", timeout=0.5)

    assert "Closed" in result
    assert "verified" in result.lower()
    assert windows == {}


def test_close_window_reports_save_dialog_without_force_closing(monkeypatch):
    windows = {
        1: {"pid": 77, "title": "Untitled - Notepad", "class": "Notepad"}
    }
    _fake_win32(monkeypatch, windows, close_behavior="save_dialog")

    result = computer_control._close_window("Notepad", timeout=0.1)

    assert "save or confirmation dialog remains" in result.lower()
    assert windows[2]["title"] == "Save As"


def test_close_window_does_not_close_ambiguous_matches(monkeypatch):
    windows = {
        1: {"pid": 77, "title": "Untitled - Notepad", "class": "Notepad"},
        2: {"pid": 88, "title": "Notes - Notepad", "class": "Notepad"},
    }
    _fake_win32(monkeypatch, windows)
    result = computer_control._close_window("Notepad", timeout=0.1)

    assert "ambiguous" in result.lower()
    assert len(windows) == 2


def test_close_window_reports_timeout_without_success(monkeypatch):
    windows = {
        1: {"pid": 77, "title": "Untitled - Notepad", "class": "Notepad"}
    }
    _fake_win32(monkeypatch, windows, close_behavior="leave_open")

    result = computer_control._close_window("Notepad", timeout=0.1)

    assert "not verified" in result.lower()
    assert "visible window" in result.lower()


def test_alt_f4_is_not_described_as_a_verified_close(monkeypatch):
    calls = []
    monkeypatch.setattr(computer_control, "_require_pyautogui", lambda: None)
    monkeypatch.setattr(
        computer_control,
        "pyautogui",
        SimpleNamespace(hotkey=lambda *keys: calls.append(keys)),
        raising=False,
    )

    result = computer_control._hotkey("alt", "f4")

    assert calls == [("alt", "f4")]
    assert "unverified" in result.lower()
    assert "closed" in result.lower()
