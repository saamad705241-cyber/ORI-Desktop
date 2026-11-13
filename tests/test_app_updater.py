import zipfile
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


def test_repository_config_requires_owner_and_repo(monkeypatch):
    monkeypatch.setenv("ORI_GITHUB_REPOSITORY", "bad value")
    assert updater.configured_repository() == ""
    monkeypatch.setenv("ORI_GITHUB_REPOSITORY", "samad/ori")
    assert updater.configured_repository() == "samad/ori"


def test_update_check_reports_unconfigured_repository(monkeypatch):
    monkeypatch.delenv("ORI_GITHUB_REPOSITORY", raising=False)
    monkeypatch.setattr(updater, "configured_repository", lambda: "")
    result = updater.check_for_updates(repo="")
    assert result["ok"] is False
    assert result["configured"] is False


def test_release_check_compares_semver_and_finds_checksum_asset(monkeypatch):
    assets = [
        {"name": "ORI-3.6.0-Windows.zip", "browser_download_url": "https://example.test/app.zip"},
        {"name": "ORI-3.6.0-Windows.zip.sha256", "browser_download_url": "https://example.test/app.zip.sha256"},
    ]
    response = FakeResponse(payload={
        "tag_name": "v3.6.0",
        "html_url": "https://github.com/samad/ori/releases/tag/v3.6.0",
        "body": "Release notes",
        "assets": assets,
    })
    monkeypatch.setattr(updater.requests, "get", lambda *_a, **_k: response)
    result = updater.check_for_updates(repo="samad/ori", current_version="3.5.0")
    assert result["ok"] is True
    assert result["update_available"] is True
    assert result["asset"]["name"].endswith("-Windows.zip")
    assert result["checksum_asset"]["name"].endswith(".sha256")


def test_safe_extract_rejects_path_traversal(tmp_path):
    archive = tmp_path / "bad.zip"
    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr("../escape.txt", "bad")
    try:
        updater._safe_extract(archive, tmp_path / "stage")
    except ValueError as exc:
        assert "unsafe path" in str(exc).lower()
    else:
        raise AssertionError("Unsafe archive path was accepted")


def test_update_install_is_disabled_for_source_runs(monkeypatch, tmp_path):
    monkeypatch.setattr(updater.sys, "frozen", False, raising=False)
    result = updater.schedule_windows_update(str(tmp_path))
    assert result["ok"] is False
    assert "packaged Windows" in result["message"]


def test_download_update_verifies_sha256_and_extracts(monkeypatch, tmp_path):
    import hashlib
    
    archive_path = tmp_path / "payload.zip"
    with zipfile.ZipFile(archive_path, "w") as zf:
        zf.writestr("ORI/readme.txt", "verified")
    archive_bytes = archive_path.read_bytes()
    digest = hashlib.sha256(archive_bytes).hexdigest()
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "local"))

    def fake_get(url, **_kwargs):
        if url.endswith(".sha256"):
            return FakeResponse(content=f"{digest}  ORI-3.6.0-Windows.zip\n".encode())
        return FakeResponse(content=archive_bytes)

    monkeypatch.setattr(updater.requests, "get", fake_get)
    info = {
        "ok": True,
        "update_available": True,
        "latest_version": "3.6.0",
        "tag_name": "v3.6.0",
        "asset": {"name": "ORI-3.6.0-Windows.zip", "browser_download_url": "https://test/app.zip"},
        "checksum_asset": {"name": "ORI-3.6.0-Windows.zip.sha256", "browser_download_url": "https://test/app.zip.sha256"},
    }
    result = updater.download_latest_update(info)
    assert result["ok"] is True
    assert Path(result["staged_dir"]).exists()
    assert (Path(result["staged_dir"]) / "ORI" / "readme.txt").read_text() == "verified"


def test_download_update_rejects_checksum_mismatch(monkeypatch, tmp_path):
    import zipfile as _zipfile
    archive = tmp_path / "payload.zip"
    with _zipfile.ZipFile(archive, "w") as zf:
        zf.writestr("ORI/file.txt", "not trusted")
    payload = archive.read_bytes()
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "local"))

    def fake_get(url, **_kwargs):
        if url.endswith(".sha256"):
            return FakeResponse(content=("0" * 64).encode())
        return FakeResponse(content=payload)

    monkeypatch.setattr(updater.requests, "get", fake_get)
    info = {
        "ok": True, "update_available": True, "latest_version": "3.6.0", "tag_name": "v3.6.0",
        "asset": {"name": "ORI-3.6.0-Windows.zip", "browser_download_url": "https://test/app.zip"},
        "checksum_asset": {"name": "ORI-3.6.0-Windows.zip.sha256", "browser_download_url": "https://test/app.zip.sha256"},
    }
    result = updater.download_latest_update(info)
    assert result["ok"] is False
    assert "SHA-256" in result["message"]


def test_schedule_windows_update_launches_logged_verified_powershell_helper(
    monkeypatch, tmp_path
):
    install_dir = tmp_path / "installed"
    staged_dir = tmp_path / "staged"
    install_dir.mkdir()
    staged_dir.mkdir()
    installed_exe = install_dir / "ORI.exe"
    staged_exe = staged_dir / "ORI.exe"
    installed_exe.write_bytes(b"old-installed-build")
    staged_exe.write_bytes(b"new-staged-build")

    monkeypatch.setattr(updater, "platform_name", lambda: "Windows")
    monkeypatch.setattr(updater.sys, "frozen", True, raising=False)
    monkeypatch.setattr(updater.sys, "executable", str(installed_exe), raising=False)
    monkeypatch.setattr(updater.sys, "_MEIPASS", str(tmp_path / "bundle"), raising=False)
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "local"))

    bundled_core = tmp_path / "bundle" / "core"
    bundled_core.mkdir(parents=True)
    helper_source = Path(updater.__file__).resolve().with_name("apply_update.ps1")
    (bundled_core / "apply_update.ps1").write_text(
        helper_source.read_text(encoding="utf-8"),
        encoding="utf-8",
    )

    captured = {}

    def fake_popen(command, **kwargs):
        captured["command"] = command
        captured["kwargs"] = kwargs
        return object()

    monkeypatch.setattr(updater.subprocess, "Popen", fake_popen)

    result = updater.schedule_windows_update(str(staged_dir))

    assert result["ok"] is True
    assert "verify the installed executable" in result["message"]
    command = captured["command"]
    assert command[0].lower() == "powershell.exe"
    assert "-File" in command
    helper_path = Path(command[command.index("-File") + 1])
    assert helper_path.is_file()
    script = helper_path.read_text(encoding="utf-8")
    assert "Wait-Process -Id $AppPid -Timeout 120" in script
    assert "Get-FileHash -LiteralPath $sourceExe -Algorithm SHA256" in script
    assert "Invoke-VerifiedRobocopy -From $SourceDir -To $InstallDir" in script
    assert "ROLLBACK SUCCESS" in script
    assert '"api_keys.json"' in script
    assert 'Join-Path "config" "certs"' in script
    assert "/XF" in script
    assert str(staged_dir) in command
    assert str(install_dir) in command
    assert result["log_file"].endswith(".log")
    assert captured["kwargs"]["cwd"] == str(install_dir)


def test_schedule_windows_update_rejects_staged_folder_without_ori_exe(
    monkeypatch, tmp_path
):
    install_dir = tmp_path / "installed"
    install_dir.mkdir()
    (install_dir / "ORI.exe").write_bytes(b"old")
    staged_dir = tmp_path / "staged"
    staged_dir.mkdir()

    monkeypatch.setattr(updater, "platform_name", lambda: "Windows")
    monkeypatch.setattr(updater.sys, "frozen", True, raising=False)
    monkeypatch.setattr(updater.sys, "executable", str(install_dir / "ORI.exe"), raising=False)

    result = updater.schedule_windows_update(str(staged_dir))

    assert result["ok"] is False
    assert "staged update does not contain ORI.exe" in result["message"]
