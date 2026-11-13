from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_windows_location_foundation_is_installed_and_packaged():
    requirements = (ROOT / "requirements.txt").read_text(encoding="utf-8")
    build = (ROOT / "scripts" / "build_release.ps1").read_text(encoding="utf-8")
    ci = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")

    assert "winrt-Windows.Foundation>=3.2,<5; sys_platform == \"win32\"" in requirements
    assert "--collect-all winrt.windows.foundation" in build
    assert "--collect-all winrt.windows.foundation.collections" in build
    assert "from winrt.windows.foundation import Uri" in ci
    assert "from winrt.windows.devices.geolocation import Geolocator" in ci
