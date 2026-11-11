"""GitHub Releases updater for portable ORI Windows builds.

The repository name is configured by the project owner in config/api_keys.json
(`github_repository: "OWNER/REPOSITORY"`). Public release checks need no token.
Release ZIPs are accepted only with a matching SHA-256 sidecar. Source/development
runs may download and verify a release, but automatic replacement is restricted
to a frozen one-folder Windows build.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path
from typing import Any

import requests

from ori_metadata import APP_VERSION

_REPO_RE = re.compile(r"^[A-Za-z0-9_.-]{1,100}/[A-Za-z0-9_.-]{1,100}$")
_MAX_DOWNLOAD = 600 * 1024 * 1024


def configured_repository() -> str:
    value = os.environ.get("ORI_GITHUB_REPOSITORY", "").strip()
    if not value:
        try:
            from memory.config_manager import load_api_keys
            value = str(load_api_keys().get("github_repository", "") or "").strip()
        except Exception:
            value = ""
    return value if _REPO_RE.fullmatch(value) else ""


def _version_tuple(tag: str) -> tuple[int, ...]:
    text = str(tag or "").strip().lstrip("vV")
    match = re.match(r"^(\d+(?:\.\d+){0,3})", text)
    if not match:
        return (0,)
    return tuple(int(part) for part in match.group(1).split("."))


def check_for_updates(repo: str | None = None, current_version: str = APP_VERSION,
                      timeout: float = 8.0) -> dict[str, Any]:
    repository = (repo or configured_repository()).strip()
    if not _REPO_RE.fullmatch(repository):
        return {
            "ok": False,
            "configured": False,
            "message": "The official GitHub repository is not connected yet. Set github_repository in config/api_keys.json after the repository is created.",
        }
    url = f"https://api.github.com/repos/{repository}/releases/latest"
    try:
        response = requests.get(
            url,
            headers={"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"},
            timeout=max(2.0, min(float(timeout), 20.0)),
        )
        if response.status_code == 404:
            return {"ok": False, "configured": True, "message": "No published ORI release was found in this repository yet."}
        response.raise_for_status()
        release = response.json()
        tag = str(release.get("tag_name") or "")
        assets = release.get("assets") if isinstance(release.get("assets"), list) else []
        windows_asset = next((a for a in assets if str(a.get("name", "")).lower().endswith("-windows.zip")), None)
        checksum_asset = None
        if windows_asset:
            expected = str(windows_asset.get("name", "")) + ".sha256"
            checksum_asset = next((a for a in assets if a.get("name") == expected), None)
        return {
            "ok": True,
            "configured": True,
            "repository": repository,
            "current_version": str(current_version),
            "latest_version": tag.lstrip("vV"),
            "tag_name": tag,
            "update_available": _version_tuple(tag) > _version_tuple(current_version),
            "release_url": str(release.get("html_url") or f"https://github.com/{repository}/releases"),
            "release_notes": str(release.get("body") or "")[:4000],
            "asset": windows_asset,
            "checksum_asset": checksum_asset,
            "message": "Update available." if _version_tuple(tag) > _version_tuple(current_version) else "ORI is up to date.",
        }
    except requests.Timeout:
        return {"ok": False, "configured": True, "message": "GitHub did not respond before the update check timed out."}
    except requests.RequestException as exc:
        return {"ok": False, "configured": True, "message": f"Could not check GitHub releases: {type(exc).__name__}: {exc}"}
    except (ValueError, TypeError) as exc:
        return {"ok": False, "configured": True, "message": f"GitHub returned an invalid release response: {type(exc).__name__}."}


def _download(url: str, target: Path, timeout: float = 30.0) -> None:
    total = 0
    with requests.get(url, stream=True, timeout=(8, max(5.0, min(timeout, 90.0))),
                      headers={"Accept": "application/octet-stream"}) as response:
        response.raise_for_status()
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("wb") as output:
            for chunk in response.iter_content(1024 * 256):
                if not chunk:
                    continue
                total += len(chunk)
                if total > _MAX_DOWNLOAD:
                    raise ValueError("Update package exceeds the 600 MB safety limit.")
                output.write(chunk)


def _safe_extract(archive: Path, destination: Path) -> None:
    destination = destination.resolve()
    with zipfile.ZipFile(archive) as zf:
        for info in zf.infolist():
            member = (destination / info.filename).resolve()
            if destination != member and destination not in member.parents:
                raise ValueError("Update archive contains an unsafe path.")
        zf.extractall(destination)


def download_latest_update(info: dict[str, Any] | None = None) -> dict[str, Any]:
    info = info or check_for_updates()
    if not info.get("ok") or not info.get("update_available"):
        return {"ok": False, "message": str(info.get("message") or "No update is available.")}
    asset = info.get("asset")
    checksum = info.get("checksum_asset")
    if not isinstance(asset, dict) or not isinstance(checksum, dict):
        return {"ok": False, "message": "The release is missing its Windows ZIP or SHA-256 checksum asset."}
    name = Path(str(asset.get("name") or "ORI-update-Windows.zip")).name
    home = Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "ORI" / "updates"
    download_dir = home / str(info.get("tag_name", "latest")).replace("/", "_")
    archive = download_dir / name
    checksum_file = download_dir / (name + ".sha256")
    try:
        _download(str(asset.get("browser_download_url") or ""), archive)
        _download(str(checksum.get("browser_download_url") or ""), checksum_file)
        expected_text = checksum_file.read_text(encoding="utf-8", errors="replace").strip()
        match = re.search(r"\b([a-fA-F0-9]{64})\b", expected_text)
        if not match:
            raise ValueError("Release checksum file does not contain a SHA-256 digest.")
        digest = hashlib.sha256(archive.read_bytes()).hexdigest()
        if digest.lower() != match.group(1).lower():
            archive.unlink(missing_ok=True)
            raise ValueError("Downloaded update failed SHA-256 verification; the package was discarded.")
        stage = download_dir / "staged"
        if stage.exists():
            shutil.rmtree(stage)
        stage.mkdir(parents=True, exist_ok=True)
        _safe_extract(archive, stage)
        # PyInstaller release workflow stores its one-folder payload in ORI/.
        source = stage / "ORI" if (stage / "ORI" / "ORI.exe").exists() else stage
        return {
            "ok": True,
            "version": info.get("latest_version"),
            "archive": str(archive),
            "staged_dir": str(source),
            "sha256": digest,
            "message": f"ORI {info.get('latest_version')} downloaded and SHA-256 verified.",
        }
    except Exception as exc:
        return {"ok": False, "message": f"Update download/verification failed: {type(exc).__name__}: {exc}"}


def schedule_windows_update(staged_dir: str) -> dict[str, Any]:
    """Apply a verified one-folder update after ORI exits (frozen Windows only)."""
    if platform_name() != "Windows" or not getattr(sys, "frozen", False):
        return {"ok": False, "message": "Automatic replacement is available only in the packaged Windows release. Source installs must be updated from the repository."}
    app_dir = Path(sys.executable).resolve().parent
    source = Path(staged_dir).resolve()
    exe = app_dir / "ORI.exe"
    if not exe.exists() or not source.exists():
        return {"ok": False, "message": "The installed ORI folder or staged update package is missing."}
    helper = Path(tempfile.gettempdir()) / f"ori_apply_update_{os.getpid()}.bat"
    helper.write_text(
        "@echo off\r\n"
        "setlocal\r\n"
        f'set "APP_DIR={app_dir}"\r\n'
        f'set "SRC_DIR={source}"\r\n'
        f'set "APP_PID={os.getpid()}"\r\n'
        ':wait_app\r\n'
        'tasklist /FI "PID eq %APP_PID%" 2>nul | find "%APP_PID%" >nul\r\n'
        'if not errorlevel 1 (timeout /t 1 /nobreak >nul & goto wait_app)\r\n'
        'robocopy "%SRC_DIR%" "%APP_DIR%" /E /R:3 /W:2 /XD "%APP_DIR%\\memory" "%APP_DIR%\\downloads" "%APP_DIR%\\screenshots" "%APP_DIR%\\logs" "%APP_DIR%\\config\\certs" /XF api_keys.json *.log\r\n'
        'if %ERRORLEVEL% GEQ 8 exit /b 1\r\n'
        'start "" "%APP_DIR%\\ORI.exe"\r\n'
        'exit /b 0\r\n',
        encoding="utf-8",
    )
    flags = getattr(subprocess, "DETACHED_PROCESS", 0x00000008) | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0x00000200)
    subprocess.Popen(["cmd.exe", "/c", str(helper)], creationflags=flags,
                     close_fds=True, cwd=str(app_dir))
    return {"ok": True, "message": "Update staged. ORI will close and restart after the updater replaces program files. Personal config and memory are preserved."}


def platform_name() -> str:
    import platform
    return platform.system()
