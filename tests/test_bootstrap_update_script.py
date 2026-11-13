from pathlib import Path


def _bootstrap_source() -> str:
    return (
        Path(__file__).resolve().parents[1] / "scripts" / "bootstrap_update.ps1"
    ).read_text(encoding="utf-8")


def test_bootstrap_finds_the_running_ori_process_without_guessing_install_path():
    source = _bootstrap_source()
    assert 'Get-Process -Name "ORI"' in source
    assert "MainModule.FileName" in source
    assert "More than one ORI.exe process is running" in source


def test_bootstrap_downloads_exact_latest_release_and_verifies_sha256():
    source = _bootstrap_source()
    assert "/releases/latest" in source
    assert 'ORI-$version-Windows.zip' in source
    assert '$checksumName = "$zipName.sha256"' in source
    assert "Get-FileHash -LiteralPath $zipPath -Algorithm SHA256" in source
    assert "The downloaded package was discarded" in source


def test_bootstrap_requires_official_release_and_included_installer_helper():
    source = _bootstrap_source()
    assert "$uri.Host -ne " in source
    assert "ORI/core/apply_update.ps1" in source
    assert "Join-Path $sourceDir" in source
    assert "apply_update.ps1" in source


def test_bootstrap_starts_helper_then_closes_the_current_app():
    source = _bootstrap_source()
    assert "Start-Process -FilePath $windowsPowerShell" in source
    assert "$oriProcess.CloseMainWindow()" in source
    assert "bootstrap-$version-$appPid.log" in source
