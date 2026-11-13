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
    """Launch a logged PowerShell installer which verifies copy and restart."""
    if platform_name() != "Windows" or not getattr(sys, "frozen", False):
        return {
            "ok": False,
            "message": (
                "Automatic replacement is available only in the packaged Windows release. "
                "Source installs must be updated from the repository."
            ),
        }

    app_dir = Path(sys.executable).resolve().parent
    source = Path(staged_dir).resolve()
    installed_exe = app_dir / "ORI.exe"
    staged_exe = source / "ORI.exe"
    if not installed_exe.is_file():
        return {"ok": False, "message": f"The installed ORI executable is missing: {installed_exe}"}
    if not staged_exe.is_file():
        return {"ok": False, "message": f"The staged update does not contain ORI.exe: {staged_exe}"}

    bundled_root = Path(getattr(sys, "_MEIPASS", app_dir)).resolve()
    helper_source = bundled_root / "core" / "apply_update.ps1"
    if not helper_source.is_file():
        helper_source = Path(__file__).resolve().with_name("apply_update.ps1")
    if not helper_source.is_file():
        return {"ok": False, "message": f"The update helper is missing from this package: {helper_source}"}

    state_dir = (
        Path(os.environ.get("LOCALAPPDATA", str(Path.home())))
        / "ORI" / "updates" / "install-helper"
    )
    try:
        state_dir.mkdir(parents=True, exist_ok=True)
        helper = state_dir / f"apply-update-{os.getpid()}.ps1"
        log_file = state_dir / f"install-{APP_VERSION}-{os.getpid()}.log"
        rollback_dir = state_dir / f"rollback-{APP_VERSION}-{os.getpid()}"
        shutil.copy2(helper_source, helper)
        command = [
            "powershell.exe", "-NoLogo", "-NoProfile", "-NonInteractive",
            "-ExecutionPolicy", "Bypass", "-File", str(helper),
            "-AppPid", str(os.getpid()),
            "-SourceDir", str(source),
            "-InstallDir", str(app_dir),
            "-LogPath", str(log_file),
            "-RollbackDir", str(rollback_dir),
        ]
        flags = (
            getattr(subprocess, "DETACHED_PROCESS", 0x00000008)
            | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0x00000200)
            | getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)
        )
        subprocess.Popen(
            command, creationflags=flags, close_fds=True, cwd=str(app_dir),
            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
    except Exception as exc:
        return {"ok": False, "message": f"Could not launch the update installer: {type(exc).__name__}: {exc}"}

    return {
        "ok": True,
        "log_file": str(log_file),
        "message": (
            "Update installer started. ORI will close, copy the new program files, "
            "verify the installed executable and restart. If installation fails, "
            f"the previous build will be restored. Details: {log_file}"
        ),
    }

def platform_name() -> str:
    import platform
    return platform.system()
