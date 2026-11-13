from types import SimpleNamespace

from actions import open_app


def test_windows_app_visibility_checks_process_name(monkeypatch):
    fake_psutil = SimpleNamespace(
        process_iter=lambda attrs: [
            SimpleNamespace(info={"name": "notepad.exe", "exe": r"C:\Windows\System32\notepad.exe"})
        ]
    )
    monkeypatch.setattr(open_app, "psutil", fake_psutil)
    monkeypatch.setattr(open_app, "_PSUTIL", True)
    monkeypatch.setattr(open_app, "platform", SimpleNamespace(system=lambda: "Windows"))

    assert open_app._windows_app_visible("notepad.exe") is True


def test_windows_launcher_requires_post_launch_verification(monkeypatch):
    launched = []
    monkeypatch.setattr(open_app.shutil, "which", lambda _name: r"C:\Windows\System32\notepad.exe")
    monkeypatch.setattr(open_app.subprocess, "Popen", lambda *args, **kwargs: launched.append(args))
    monkeypatch.setattr(open_app, "_wait_for_windows_app", lambda _name: False)

    assert open_app._launch_windows("notepad.exe") is False
    assert launched


def test_open_app_reports_unverified_when_launcher_cannot_confirm(monkeypatch):
    monkeypatch.setattr(open_app, "_SYSTEM", "Windows")
    monkeypatch.setitem(open_app._OS_LAUNCHERS, "Windows", lambda _name: False)

    result = open_app.open_app({"app_name": "Notepad"})

    assert "not confirmed" in result.lower()
    assert "will not claim it opened" in result.lower()


def test_open_app_only_reports_success_after_launcher_confirmation(monkeypatch):
    monkeypatch.setattr(open_app, "_SYSTEM", "Windows")
    monkeypatch.setitem(open_app._OS_LAUNCHERS, "Windows", lambda _name: True)

    result = open_app.open_app({"app_name": "Notepad"})

    assert "verified" in result.lower()
