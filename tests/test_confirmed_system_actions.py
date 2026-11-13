from types import SimpleNamespace

import pytest

from actions import computer_settings


def test_windows_restart_reports_scheduled_not_completed(monkeypatch):
    calls = []
    monkeypatch.setattr(computer_settings, "_OS", "Windows")
    monkeypatch.setattr(
        computer_settings.subprocess,
        "run",
        lambda command, **kwargs: calls.append(command) or SimpleNamespace(
            returncode=0, stdout="", stderr=""
        ),
    )

    result = computer_settings.restart_computer()

    assert calls == [["shutdown", "/r", "/t", "10"]]
    assert "accepted the restart request" in result
    assert "has not happened yet" in result


def test_windows_shutdown_does_not_report_success_when_os_rejects_command(monkeypatch):
    monkeypatch.setattr(computer_settings, "_OS", "Windows")
    monkeypatch.setattr(
        computer_settings.subprocess,
        "run",
        lambda *_args, **_kwargs: SimpleNamespace(
            returncode=1, stdout="", stderr="Access is denied."
        ),
    )

    with pytest.raises(RuntimeError, match="Access is denied"):
        computer_settings.shutdown_computer()


def test_linux_wifi_uses_nmcli_on_off_arguments_and_verifies_readback(monkeypatch):
    calls = []
    responses = [
        SimpleNamespace(returncode=0, stdout="enabled\n", stderr=""),
        SimpleNamespace(returncode=0, stdout="", stderr=""),
        SimpleNamespace(returncode=0, stdout="disabled\n", stderr=""),
    ]

    def fake_run(command, **_kwargs):
        calls.append(command)
        return responses.pop(0)

    monkeypatch.setattr(computer_settings, "_OS", "Linux")
    monkeypatch.setattr(computer_settings.subprocess, "run", fake_run)

    result = computer_settings.toggle_wifi()

    assert calls[0] == ["nmcli", "-t", "-f", "WIFI", "radio"]
    assert calls[1] == ["nmcli", "radio", "wifi", "off"]
    assert calls[2] == ["nmcli", "-t", "-f", "WIFI", "radio"]
    assert "Verified by nmcli" in result


def test_linux_wifi_reports_unverified_when_radio_state_did_not_change(monkeypatch):
    responses = [
        SimpleNamespace(returncode=0, stdout="enabled\n", stderr=""),
        SimpleNamespace(returncode=0, stdout="", stderr=""),
        SimpleNamespace(returncode=0, stdout="enabled\n", stderr=""),
    ]
    monkeypatch.setattr(computer_settings, "_OS", "Linux")
    monkeypatch.setattr(computer_settings.subprocess, "run", lambda *_a, **_k: responses.pop(0))

    with pytest.raises(RuntimeError, match="did not change"):
        computer_settings.toggle_wifi()
