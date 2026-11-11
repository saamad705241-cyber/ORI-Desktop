import json
import subprocess

from actions import windows_update as wu


def test_check_windows_updates_parses_pending_list(monkeypatch):
    result = {"ok": True, "pending_count": 1, "updates": [{"title": "Security update"}]}
    monkeypatch.setattr(wu.platform, "system", lambda: "Windows")
    monkeypatch.setattr(
        wu, "_powershell",
        lambda *_a, **_k: subprocess.CompletedProcess([], 0, json.dumps(result), ""),
    )
    assert wu.check_windows_updates() == result


def test_check_windows_updates_has_bounded_timeout(monkeypatch):
    monkeypatch.setattr(wu.platform, "system", lambda: "Windows")
    def timeout(*_a, **_k):
        raise subprocess.TimeoutExpired("powershell", 28)
    monkeypatch.setattr(wu, "_powershell", timeout)
    data = wu.check_windows_updates(timeout=28)
    assert data["ok"] is False
    assert data["timeout"] is True


def test_non_windows_update_check_is_explicit(monkeypatch):
    monkeypatch.setattr(wu.platform, "system", lambda: "Linux")
    assert wu.check_windows_updates()["ok"] is False


def test_windows_update_check_reports_user_cancellation(monkeypatch):
    monkeypatch.setattr(wu.platform, "system", lambda: "Windows")
    def cancelled(*_args, **_kwargs):
        raise InterruptedError("cancelled")
    monkeypatch.setattr(wu, "_powershell", cancelled)
    result = wu.check_windows_updates()
    assert result["ok"] is False
    assert result["cancelled"] is True
