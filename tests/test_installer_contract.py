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
    assert "$ExpectedVersion" in source
    assert "$startup.version" in source
    assert "$startup.executable" in source
    assert "15-second post-start stability check" in source
    assert "[switch]$NoDialog" in source
    assert "if (!$NoDialog)" in source
    assert "$newProcess.Refresh()" in source
    assert "at the end of the 15-second post-start stability check" in source
    assert "$previousRegisteredVersion" in source
    assert "Set-ItemProperty -LiteralPath $previousUninstallKey -Name DisplayVersion" in source


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


def test_ci_exercises_a_real_in_place_upgrade_from_published_362():
    workflow = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    assert "ORI-Setup-3.6.2.exe" in workflow
    assert "core/install_update.ps1" in workflow
    assert "UPDATE SUCCESS" in workflow
    assert "-ExpectedVersion $version" in workflow
    assert "DisplayVersion" in workflow
    assert "ci-update-preservation.txt" in workflow
    assert "3.6.2 -> $version" in workflow



def test_update_startup_marker_reports_version_and_executable_identity():
    source = (ROOT / "main.py").read_text(encoding="utf-8")
    assert '"version": APP_VERSION' in source
    assert '"executable": os.path.normcase(os.path.abspath(sys.executable))' in source



def test_settings_uses_one_progressive_update_button():
    source = (ROOT / "ui.py").read_text(encoding="utf-8")
    assert 'self._update_action_btn = button("CHECK FOR UPDATES", True)' in source
    assert 'self._update_action_btn.clicked.connect(self._handle_update_action)' in source
    assert '"download": "DOWNLOAD UPDATE"' in source
    assert '"install": "INSTALL & RESTART"' in source
    assert "def _handle_update_action(self)" in source
    assert "_check_updates_btn" not in source
    assert "_download_update_btn" not in source
    assert "_install_update_btn" not in source
