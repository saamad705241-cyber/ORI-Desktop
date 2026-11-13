from types import SimpleNamespace

from actions import desktop


def test_windows_wallpaper_reports_failure_when_system_api_rejects_change(monkeypatch, tmp_path):
    image = tmp_path / "wallpaper.jpg"
    image.write_bytes(b"fake-image")
    monkeypatch.setattr(desktop, "_OS", "Windows")
    monkeypatch.setattr(
        "ctypes.windll",
        SimpleNamespace(user32=SimpleNamespace(SystemParametersInfoW=lambda *_args: 0)),
        raising=False,
    )

    result = desktop.set_wallpaper(str(image))

    assert "Could not set wallpaper" in result
    assert "rejected" in result.lower()


def test_windows_wallpaper_reports_success_only_after_api_accepts(monkeypatch, tmp_path):
    image = tmp_path / "wallpaper.jpg"
    image.write_bytes(b"fake-image")
    monkeypatch.setattr(desktop, "_OS", "Windows")
    monkeypatch.setattr(
        "ctypes.windll",
        SimpleNamespace(user32=SimpleNamespace(SystemParametersInfoW=lambda *_args: 1)),
        raising=False,
    )

    result = desktop.set_wallpaper(str(image))

    assert "Verified" in result
    assert "wallpaper.jpg" in result


def test_macos_wallpaper_checks_osascript_return_code(monkeypatch, tmp_path):
    image = tmp_path / "wallpaper.jpg"
    image.write_bytes(b"fake-image")
    monkeypatch.setattr(desktop, "_OS", "Darwin")
    monkeypatch.setattr(
        desktop.subprocess,
        "run",
        lambda *_args, **_kwargs: SimpleNamespace(returncode=1, stderr="permission denied", stdout=""),
    )

    result = desktop.set_wallpaper(str(image))

    assert "Could not set wallpaper" in result
    assert "permission denied" in result


def test_linux_wallpaper_checks_desktop_command_return_code(monkeypatch, tmp_path):
    image = tmp_path / "wallpaper.jpg"
    image.write_bytes(b"fake-image")
    monkeypatch.setattr(desktop, "_OS", "Linux")
    monkeypatch.setenv("XDG_CURRENT_DESKTOP", "GNOME")
    monkeypatch.setattr(
        desktop.subprocess,
        "run",
        lambda *_args, **_kwargs: SimpleNamespace(returncode=1, stderr="gsettings failed", stdout=""),
    )

    result = desktop.set_wallpaper(str(image))

    assert "Could not set wallpaper" in result
    assert "gsettings failed" in result
