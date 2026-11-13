from actions import computer_settings


def test_close_app_routes_to_verified_window_helper_without_pyautogui(monkeypatch):
    captured = []
    monkeypatch.setattr(computer_settings, "_PYAUTOGUI", False)
    monkeypatch.setattr(
        "actions.computer_control._close_window",
        lambda title: captured.append(title) or f"Verified close: {title}",
    )

    result = computer_settings.computer_settings({
        "action": "close_app",
        "value": "Notepad",
    })

    assert result == "Verified close: Notepad"
    assert captured == ["Notepad"]


def test_close_app_requires_a_specific_target(monkeypatch):
    monkeypatch.setattr(computer_settings, "_PYAUTOGUI", False)

    result = computer_settings.computer_settings({"action": "close_app"})

    assert "specify the application or window title" in result
    assert "No keyboard shortcut was sent" in result


def test_volume_set_reports_success_only_after_readback(monkeypatch):
    readings = iter([40, 60])
    monkeypatch.setattr(computer_settings, "_PYAUTOGUI", True)
    monkeypatch.setattr(computer_settings, "volume_get", lambda: next(readings))
    captured = []
    monkeypatch.setattr(computer_settings, "volume_set", lambda value: captured.append(value))
    monkeypatch.setattr(computer_settings, "push_undo", lambda *_args: None)

    result = computer_settings.computer_settings({
        "action": "volume_set",
        "value": "60",
    })

    assert captured == [60]
    assert "Verified by reading the device level back" in result


def test_volume_set_does_not_claim_success_when_readback_is_missing(monkeypatch):
    readings = iter([40, None])
    monkeypatch.setattr(computer_settings, "_PYAUTOGUI", True)
    monkeypatch.setattr(computer_settings, "volume_get", lambda: next(readings))
    monkeypatch.setattr(computer_settings, "volume_set", lambda _value: None)

    result = computer_settings.computer_settings({
        "action": "volume_set",
        "value": "60",
    })

    assert "result is unverified" in result


def test_irreversible_restart_still_requests_confirmation_without_pyautogui(monkeypatch):
    captured = {}
    monkeypatch.setattr(computer_settings, "_PYAUTOGUI", False)
    monkeypatch.setitem(computer_settings.ACTION_MAP, "restart", lambda: "Restart scheduled by the OS.")
    monkeypatch.setattr(
        computer_settings.confirm,
        "request",
        lambda **kwargs: captured.update(kwargs) or "[CONFIRMATION_PENDING]",
    )

    result = computer_settings.computer_settings({"action": "restart"})

    assert result == "[CONFIRMATION_PENDING]"
    assert captured["key"] == "restart"
    assert captured["run"]() == "Restart scheduled by the OS."
