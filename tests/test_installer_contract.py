from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_inno_setup_is_per_user_with_shortcuts_and_uninstaller():
    source = (ROOT / "installer" / "ORI.iss").read_text(encoding="utf-8")
    assert "PrivilegesRequired=lowest" in source
    assert "DefaultDirName={localappdata}\\Programs\\ORI" in source
    assert 'Name: "{autoprograms}\\ORI"' in source
    assert 'Name: "{autodesktop}\\ORI"' in source
    assert "Uninstallable=yes" in source
    assert "UninstallDisplayName=ORI Personal AI Desktop Assistant" in source
    assert "skipifsilent" in source


def test_installer_does_not_package_live_credentials():
    source = (ROOT / "installer" / "ORI.iss").read_text(encoding="utf-8")
    build = (ROOT / "scripts" / "build_release.ps1").read_text(encoding="utf-8")
    assert 'Excludes: "config\\api_keys.json"' in source
    assert "Copy-Item \"config\\api_keys.example.json\" \"dist\\ORI\\config\\api_keys.json\"" not in build
    assert "config/api_keys.json" not in build


def test_update_helper_runs_setup_and_requires_startup_marker_before_success():
    source = (ROOT / "core" / "install_update.ps1").read_text(encoding="utf-8")
    assert "Wait-Process -Id $AppPid -Timeout 120" in source
    assert "/VERYSILENT" in source
    assert "/CLOSEAPPLICATIONS" in source
    assert "ORI_STARTUP_TOKEN" not in source
    assert "--ori-update-token=$token" in source
    assert "UPDATE SUCCESS" in source
    assert "ROLLBACK SUCCESS" in source
    assert "startup" in source


def test_uninstaller_launcher_preserves_personal_data_folder():
    source = (ROOT / "core" / "uninstall_launcher.ps1").read_text(encoding="utf-8")
    assert "Wait-Process -Id $AppPid" in source
    assert "uninstall wizard" in source.lower()
    assert "LocalAppData\\ORI is not removed" in source


def test_user_data_paths_are_outside_the_install_directory_for_frozen_builds():
    source = (ROOT / "core" / "app_paths.py").read_text(encoding="utf-8")
    assert 'Path(sys.executable).resolve().parent' in source
    assert 'root / APP_NAME' in source
    assert '"config" / "api_keys.json"' in source
    assert '"memory" / "long_term.json"' in source
