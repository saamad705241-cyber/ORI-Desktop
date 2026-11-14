import hashlib
from pathlib import Path

from core import app_updater as updater


class FakeResponse:
    def __init__(self, status=200, payload=None, content=b""):
        self.status_code = status
        self._payload = payload or {}
        self.content = content
        self.headers = {}

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            import requests
            raise requests.HTTPError(f"HTTP {self.status_code}")

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def iter_content(self, chunk_size):
        yield self.content


def _release_payload():
    installer_name = "ORI-Setup-3.6.0.exe"
    return {
        "tag_name": "v3.6.0",
        "html_url": "https://github.com/samad/ori/releases/tag/v3.6.0",
        "body": "Release notes",
        "assets": [
            {"name": installer_name, "browser_download_url": "https://example.test/" + installer_name},
            {"name": installer_name + ".sha256", "browser_download_url": "https://example.test/" + installer_name + ".sha256"},
        ],
    }


def test_repository_config_requires_owner_and_repo(monkeypatch):
    monkeypatch.setenv("ORI_GITHUB_REPOSITORY", "bad value")
    assert updater.configured_repository() == ""
    monkeypatch.setenv("ORI_GITHUB_REPOSITORY", "samad/ori")
    assert updater.configured_repository() == "samad/ori"


def test_repository_defaults_to_official_ori_repository(monkeypatch):
    monkeypatch.delenv("ORI_GITHUB_REPOSITORY", raising=False)
    monkeypatch.setattr("memory.config_manager.load_api_keys", lambda: {"github_repository": ""})
    assert updater.configured_repository() == "saamad705241-cyber/ORI-Desktop"


def test_update_check_only_reads_release_metadata_and_finds_setup_checksum(monkeypatch):
    calls = []
    response = FakeResponse(payload=_release_payload())

    def fake_get(url, **kwargs):
        calls.append((url, kwargs))
        return response

    monkeypatch.setattr(updater.requests, "get", fake_get)
    result = updater.check_for_updates(repo="samad/ori", current_version="3.5.4")

    assert result["ok"] is True
    assert result["update_available"] is True
    assert result["asset"]["name"] == "ORI-Setup-3.6.0.exe"
    assert result["checksum_asset"]["name"] == "ORI-Setup-3.6.0.exe.sha256"
    assert len(calls) == 1
    assert calls[0][0].endswith("/releases/latest")


def test_update_check_reports_missing_setup_asset_without_downloading(monkeypatch):
    payload = _release_payload()
    payload["assets"] = []
    monkeypatch.setattr(updater.requests, "get", lambda *_a, **_k: FakeResponse(payload=payload))
    result = updater.check_for_updates(repo="samad/ori", current_version="3.5.4")
    assert result["ok"] is True
    assert result["update_available"] is True
    assert result["asset"] is None
    assert result["checksum_asset"] is None


def test_update_check_reports_unconfigured_repository(monkeypatch):
    monkeypatch.delenv("ORI_GITHUB_REPOSITORY", raising=False)
    monkeypatch.setattr(updater, "configured_repository", lambda: "")
    result = updater.check_for_updates(repo="")
    assert result["ok"] is False
    assert result["configured"] is False


def test_download_update_verifies_setup_exe_and_does_not_extract(monkeypatch, tmp_path):
    installer_bytes = b"ORI SETUP TEST EXE CONTENT"
    digest = hashlib.sha256(installer_bytes).hexdigest()
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "local"))

    def fake_get(url, **_kwargs):
        if url.endswith(".sha256"):
            return FakeResponse(content=f"{digest}  ORI-Setup-3.6.0.exe\n".encode())
        return FakeResponse(content=installer_bytes)

    monkeypatch.setattr(updater.requests, "get", fake_get)
    info = {
        "ok": True,
        "update_available": True,
        "latest_version": "3.6.0",
        "tag_name": "v3.6.0",
        "asset": {"name": "ORI-Setup-3.6.0.exe", "browser_download_url": "https://test/app.exe"},
        "checksum_asset": {"name": "ORI-Setup-3.6.0.exe.sha256", "browser_download_url": "https://test/app.exe.sha256"},
    }

    result = updater.download_latest_update(info)
    installer = Path(result["installer_path"])
    assert result["ok"] is True
    assert installer.is_file()
    assert installer.read_bytes() == installer_bytes
    assert installer.suffix.lower() == ".exe"
    assert "staged_dir" not in result


def test_download_update_rejects_checksum_mismatch_and_discards_installer(monkeypatch, tmp_path):
    installer_bytes = b"not trusted"
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "local"))

    def fake_get(url, **_kwargs):
        if url.endswith(".sha256"):
            return FakeResponse(content=("0" * 64).encode())
        return FakeResponse(content=installer_bytes)

    monkeypatch.setattr(updater.requests, "get", fake_get)
    info = {
        "ok": True, "update_available": True, "latest_version": "3.6.0", "tag_name": "v3.6.0",
        "asset": {"name": "ORI-Setup-3.6.0.exe", "browser_download_url": "https://test/app.exe"},
        "checksum_asset": {"name": "ORI-Setup-3.6.0.exe.sha256", "browser_download_url": "https://test/app.exe.sha256"},
    }
    result = updater.download_latest_update(info)
    assert result["ok"] is False
    assert "SHA-256" in result["message"]
    assert not (tmp_path / "local" / "ORI" / "updates" / "v3.6.0" / "ORI-Setup-3.6.0.exe").exists()


def test_download_rejects_non_https_release_assets(monkeypatch, tmp_path):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "local"))
    info = {
        "ok": True, "update_available": True, "latest_version": "3.6.0", "tag_name": "v3.6.0",
        "asset": {"name": "ORI-Setup-3.6.0.exe", "browser_download_url": "http://example.test/app.exe"},
        "checksum_asset": {"name": "ORI-Setup-3.6.0.exe.sha256", "browser_download_url": "https://example.test/app.exe.sha256"},
    }
    result = updater.download_latest_update(info)
    assert result["ok"] is False
    assert "HTTPS" in result["message"]


def test_update_install_is_disabled_for_source_runs(monkeypatch, tmp_path):
    monkeypatch.setattr(updater, "platform_name", lambda: "Windows")
    monkeypatch.setattr(updater.sys, "frozen", False, raising=False)
    result = updater.schedule_windows_update(str(tmp_path / "ORI-Setup.exe"))
    assert result["ok"] is False
    assert "installed Windows release" in result["message"]


def test_schedule_windows_update_launches_logged_setup_helper(monkeypatch, tmp_path):
    install_dir = tmp_path / "installed"
    install_dir.mkdir()
    (install_dir / "ORI.exe").write_bytes(b"old-installed-build")
    (install_dir / "unins000.exe").write_bytes(b"Inno uninstaller")
    installer = tmp_path / "ORI-Setup-3.6.0.exe"
    installer.write_bytes(b"verified-setup")

    monkeypatch.setattr(updater, "platform_name", lambda: "Windows")
    monkeypatch.setattr(updater.sys, "frozen", True, raising=False)
    monkeypatch.setattr(updater.sys, "executable", str(install_dir / "ORI.exe"), raising=False)
    monkeypatch.setattr(updater.sys, "_MEIPASS", str(tmp_path / "bundle"), raising=False)
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "local"))

    bundled_core = tmp_path / "bundle" / "core"
    bundled_core.mkdir(parents=True)
    helper_source = Path(updater.__file__).resolve().with_name("install_update.ps1")
    (bundled_core / "install_update.ps1").write_text(
        helper_source.read_text(encoding="utf-8"), encoding="utf-8"
    )

    captured = {}

    def fake_popen(command, **kwargs):
        captured["command"] = command
        captured["kwargs"] = kwargs
        return object()

    monkeypatch.setattr(updater.subprocess, "Popen", fake_popen)
    result = updater.schedule_windows_update(str(installer))

    assert result["ok"] is True
    assert "verify" in result["message"].lower()
    command = captured["command"]
    assert command[0].lower() == "powershell.exe"
    assert "-File" in command
    assert "-InstallerPath" in command
    assert "-InstallDir" in command
    assert "-ExpectedVersion" in command
    assert command[command.index("-ExpectedVersion") + 1] == "3.6.0"
    assert str(installer) in command
    helper_path = Path(command[command.index("-File") + 1])
    script = helper_path.read_text(encoding="utf-8")
    assert "Wait-Process -Id $AppPid -Timeout 120" in script
    assert "/VERYSILENT" in script
    assert "startup" in script
    assert "UPDATE SUCCESS" in script
    assert "ROLLBACK SUCCESS" in script
    assert result["log_file"].endswith(".log")
    assert captured["kwargs"]["cwd"] == str(install_dir)


def test_schedule_windows_update_requires_setup_managed_install(monkeypatch, tmp_path):
    install_dir = tmp_path / "portable"
    install_dir.mkdir()
    (install_dir / "ORI.exe").write_bytes(b"app")
    installer = tmp_path / "ORI-Setup-3.6.0.exe"
    installer.write_bytes(b"installer")
    monkeypatch.setattr(updater, "platform_name", lambda: "Windows")
    monkeypatch.setattr(updater.sys, "frozen", True, raising=False)
    monkeypatch.setattr(updater.sys, "executable", str(install_dir / "ORI.exe"), raising=False)

    result = updater.schedule_windows_update(str(installer))
    assert result["ok"] is False
    assert "ORI Setup" in result["message"]


def test_schedule_uninstall_uses_detached_user_visible_uninstaller(monkeypatch, tmp_path):
    install_dir = tmp_path / "installed"
    install_dir.mkdir()
    (install_dir / "ORI.exe").write_bytes(b"app")
    (install_dir / "unins000.exe").write_bytes(b"uninstall")
    monkeypatch.setattr(updater, "platform_name", lambda: "Windows")
    monkeypatch.setattr(updater.sys, "frozen", True, raising=False)
    monkeypatch.setattr(updater.sys, "executable", str(install_dir / "ORI.exe"), raising=False)
    monkeypatch.setattr(updater.sys, "_MEIPASS", str(tmp_path / "bundle"), raising=False)
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "local"))
    bundled_core = tmp_path / "bundle" / "core"
    bundled_core.mkdir(parents=True)
    helper_source = Path(updater.__file__).resolve().with_name("uninstall_launcher.ps1")
    (bundled_core / "uninstall_launcher.ps1").write_text(
        helper_source.read_text(encoding="utf-8"), encoding="utf-8"
    )
    captured = {}
    monkeypatch.setattr(
        updater.subprocess, "Popen",
        lambda command, **kwargs: captured.update(command=command, kwargs=kwargs) or object(),
    )

    result = updater.schedule_uninstall()
    assert result["ok"] is True
    assert "-UninstallerPath" in captured["command"]
    assert str(install_dir / "unins000.exe") in captured["command"]
    helper = Path(captured["command"][captured["command"].index("-File") + 1])
    assert "User data" in helper.read_text(encoding="utf-8")


def test_update_check_detects_patch_release_after_360(monkeypatch):
    payload = _release_payload()
    payload["tag_name"] = "v3.6.1"
    payload["assets"] = [
        {"name": "ORI-Setup-3.6.1.exe", "browser_download_url": "https://example.test/ORI-Setup-3.6.1.exe"},
        {"name": "ORI-Setup-3.6.1.exe.sha256", "browser_download_url": "https://example.test/ORI-Setup-3.6.1.exe.sha256"},
    ]
    monkeypatch.setattr(updater.requests, "get", lambda *_a, **_k: FakeResponse(payload=payload))

    result = updater.check_for_updates(repo="saamad705241-cyber/ORI-Desktop", current_version="3.6.0")

    assert result["ok"] is True
    assert result["update_available"] is True
    assert result["latest_version"] == "3.6.1"
    assert result["asset"]["name"] == "ORI-Setup-3.6.1.exe"



def test_schedule_windows_update_rejects_target_version_mismatch(monkeypatch, tmp_path):
    install_dir = tmp_path / "installed"
    install_dir.mkdir()
    (install_dir / "ORI.exe").write_bytes(b"old-installed-build")
    (install_dir / "unins000.exe").write_bytes(b"Inno uninstaller")
    installer = tmp_path / "ORI-Setup-3.6.1.exe"
    installer.write_bytes(b"verified-setup")
    monkeypatch.setattr(updater, "platform_name", lambda: "Windows")
    monkeypatch.setattr(updater.sys, "frozen", True, raising=False)
    monkeypatch.setattr(updater.sys, "executable", str(install_dir / "ORI.exe"), raising=False)

    result = updater.schedule_windows_update(str(installer), expected_version="3.6.2")

    assert result["ok"] is False
    assert "does not match" in result["message"]
