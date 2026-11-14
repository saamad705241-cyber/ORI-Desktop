"""GitHub Releases updater for Setup-managed ORI Windows installs.

The user explicitly controls all three stages: check, download, install. Only
versioned Inno Setup executables with a matching SHA-256 sidecar are accepted.
"""
from __future__ import annotations

import hashlib
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

import requests

from ori_metadata import APP_VERSION

_REPO_RE = re.compile(r"^[A-Za-z0-9_.-]{1,100}/[A-Za-z0-9_.-]{1,100}$")
_SETUP_RE = re.compile(r"^ORI-Setup-(\d+(?:\.\d+){1,2})\.exe$", re.IGNORECASE)
DEFAULT_REPOSITORY = "saamad705241-cyber/ORI-Desktop"
_MAX_DOWNLOAD = 700 * 1024 * 1024


def _local_app_data() -> Path:
    return Path(os.environ.get("LOCALAPPDATA") or (Path.home() / "AppData" / "Local"))


def configured_repository() -> str:
    value = os.environ.get("ORI_GITHUB_REPOSITORY", "").strip()
    if not value:
        try:
            from memory.config_manager import load_api_keys
            value = str(load_api_keys().get("github_repository", "") or "").strip()
        except Exception:
            value = ""
    if not value:
        value = DEFAULT_REPOSITORY
    return value if _REPO_RE.fullmatch(value) else ""


def _version_tuple(tag: str) -> tuple[int, ...]:
    text = str(tag or "").strip().lstrip("vV")
    match = re.fullmatch(r"(\d+(?:\.\d+){1,2})(?:\.\d+)?", text)
    if not match:
        return (0,)
    try:
        return tuple(int(part) for part in match.group(1).split("."))
    except ValueError:
        return (0,)


def _find_setup_assets(assets: list[dict]) -> tuple[dict | None, dict | None]:
    setup_asset = next(
        (
            asset for asset in assets
            if isinstance(asset, dict)
            and _SETUP_RE.fullmatch(str(asset.get("name") or ""))
        ),
        None,
    )
    if not setup_asset:
        return None, None
    checksum_name = str(setup_asset.get("name") or "") + ".sha256"
    checksum_asset = next(
        (
            asset for asset in assets
            if isinstance(asset, dict) and str(asset.get("name") or "") == checksum_name
        ),
        None,
    )
    return setup_asset, checksum_asset


def check_for_updates(
    repo: str | None = None,
    current_version: str = APP_VERSION,
    timeout: float = 8.0,
) -> dict[str, Any]:
    """Check release metadata only. This function never downloads a file."""
    repository = (repo or configured_repository()).strip()
    if not _REPO_RE.fullmatch(repository):
        return {
            "ok": False,
            "configured": False,
            "message": (
                "The official GitHub repository is not configured. Set "
                "github_repository in ORI Settings configuration first."
            ),
        }

    url = f"https://api.github.com/repos/{repository}/releases/latest"
    try:
        response = requests.get(
            url,
            headers={
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
            },
            timeout=max(2.0, min(float(timeout), 20.0)),
        )
        if response.status_code == 404:
            return {
                "ok": False,
                "configured": True,
                "message": "No published ORI release was found in this repository yet.",
            }
        response.raise_for_status()
        release = response.json()
        tag = str(release.get("tag_name") or "")
        latest = tag.lstrip("vV")
        available = _version_tuple(tag) > _version_tuple(current_version)
        assets = release.get("assets") if isinstance(release.get("assets"), list) else []
        setup_asset, checksum_asset = _find_setup_assets(assets)
        return {
            "ok": True,
            "configured": True,
            "repository": repository,
            "current_version": str(current_version),
            "latest_version": latest,
            "tag_name": tag,
            "update_available": available,
            "release_url": str(
                release.get("html_url") or f"https://github.com/{repository}/releases"
            ),
            "release_notes": str(release.get("body") or "")[:4000],
            "asset": setup_asset,
            "checksum_asset": checksum_asset,
            "message": "Update available." if available else "ORI is up to date.",
        }
    except requests.Timeout:
        return {
            "ok": False,
            "configured": True,
            "message": "GitHub did not respond before the update check timed out.",
        }
    except requests.RequestException as exc:
        return {
            "ok": False,
            "configured": True,
            "message": f"Could not check GitHub releases: {type(exc).__name__}: {exc}",
        }
    except (ValueError, TypeError) as exc:
        return {
            "ok": False,
            "configured": True,
            "message": f"GitHub returned an invalid release response: {type(exc).__name__}.",
        }


def _download(url: str, target: Path, timeout: float = 45.0) -> None:
    if not str(url or "").startswith("https://"):
        raise ValueError("Release asset URL must use HTTPS.")
    total = 0
    target.parent.mkdir(parents=True, exist_ok=True)
    with requests.get(
        url,
        stream=True,
        timeout=(8, max(5.0, min(float(timeout), 90.0))),
        headers={"Accept": "application/octet-stream"},
    ) as response:
        response.raise_for_status()
        with target.open("wb") as output:
            for chunk in response.iter_content(1024 * 256):
                if not chunk:
                    continue
                total += len(chunk)
                if total > _MAX_DOWNLOAD:
                    raise ValueError("ORI Setup exceeds the 700 MB safety limit.")
                output.write(chunk)
    if total <= 0 or not target.is_file():
        raise ValueError("The release server returned an empty installer file.")


def download_latest_update(info: dict[str, Any] | None = None) -> dict[str, Any]:
    """Download the Setup EXE and verify its SHA-256; never run it."""
    info = info or check_for_updates()
    if not info.get("ok") or not info.get("update_available"):
        return {"ok": False, "message": str(info.get("message") or "No update is available.")}

    asset = info.get("asset")
    checksum = info.get("checksum_asset")
    if not isinstance(asset, dict) or not isinstance(checksum, dict):
        return {
            "ok": False,
            "message": "The release is missing its ORI Setup installer or SHA-256 checksum asset.",
        }

    asset_name = Path(str(asset.get("name") or "")).name
    if not _SETUP_RE.fullmatch(asset_name):
        return {"ok": False, "message": "The release asset is not a versioned ORI Setup executable."}
    if str(checksum.get("name") or "") != asset_name + ".sha256":
        return {"ok": False, "message": "The installer checksum sidecar does not match its file name."}

    version_dir = str(info.get("tag_name") or info.get("latest_version") or "latest")
    safe_version = re.sub(r"[^A-Za-z0-9_.-]", "_", version_dir)
    download_dir = _local_app_data() / "ORI" / "updates" / safe_version
    installer_path = download_dir / asset_name
    checksum_path = download_dir / (asset_name + ".sha256")
    try:
        _download(str(asset.get("browser_download_url") or ""), installer_path)
        _download(str(checksum.get("browser_download_url") or ""), checksum_path)
        expected_text = checksum_path.read_text(encoding="utf-8", errors="replace")
        match = re.search(r"\b([a-fA-F0-9]{64})\b", expected_text)
        if not match:
            raise ValueError("The checksum file does not contain a SHA-256 digest.")
        hasher = hashlib.sha256()
        with installer_path.open("rb") as downloaded:
            for block in iter(lambda: downloaded.read(1024 * 1024), b""):
                hasher.update(block)
        digest = hasher.hexdigest()
        if digest.lower() != match.group(1).lower():
            installer_path.unlink(missing_ok=True)
            raise ValueError("Installer SHA-256 verification failed; the file was discarded.")
        return {
            "ok": True,
            "version": info.get("latest_version"),
            "installer_path": str(installer_path),
            "sha256": digest,
            "message": f"ORI {info.get('latest_version')} Setup downloaded and SHA-256 verified.",
        }
    except Exception as exc:
        installer_path.unlink(missing_ok=True)
        return {
            "ok": False,
            "message": f"Update download/verification failed: {type(exc).__name__}: {exc}",
        }


def _launch_detached_helper(
    *,
    helper_source: Path,
    state_dir: Path,
    script_prefix: str,
    log_name: str,
    arguments: list[str],
    cwd: Path,
) -> tuple[bool, str, Path | None]:
    if not helper_source.is_file():
        return False, f"The bundled helper script is missing: {helper_source}", None

    try:
        state_dir.mkdir(parents=True, exist_ok=True)
        helper = state_dir / f"{script_prefix}-{os.getpid()}.ps1"
        log_file = state_dir / log_name
        import shutil
        shutil.copy2(helper_source, helper)
        command = [
            "powershell.exe",
            "-NoLogo",
            "-NoProfile",
            "-NonInteractive",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(helper),
            *arguments,
        ]
        flags = (
            getattr(subprocess, "DETACHED_PROCESS", 0x00000008)
            | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0x00000200)
            | getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)
        )
        subprocess.Popen(
            command,
            creationflags=flags,
            close_fds=True,
            cwd=str(cwd),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        return True, str(log_file), log_file
    except Exception as exc:
        return False, f"{type(exc).__name__}: {exc}", None


def schedule_windows_update(
    installer_path: str,
    expected_version: str | None = None,
) -> dict[str, Any]:
    """Start the detached Setup helper with an exact version to verify after relaunch."""
    if platform_name() != "Windows" or not getattr(sys, "frozen", False):
        return {
            "ok": False,
            "message": "Automatic installation is available only in the installed Windows release.",
        }

    install_dir = Path(sys.executable).resolve().parent
    installed_exe = install_dir / "ORI.exe"
    uninstaller = install_dir / "unins000.exe"
    installer = Path(installer_path).expanduser().resolve()
    setup_match = _SETUP_RE.fullmatch(installer.name)
    target_version = str(expected_version or (setup_match.group(1) if setup_match else "")).strip()
    if not re.fullmatch(r"\\d+\\.\\d+\\.\\d+", target_version):
        return {
            "ok": False,
            "message": "The downloaded installer does not contain a valid target ORI version.",
        }
    if not setup_match or setup_match.group(1) != target_version:
        return {
            "ok": False,
            "message": "The target ORI version does not match the downloaded Setup filename.",
        }
    if not installed_exe.is_file():
        return {"ok": False, "message": f"The installed ORI executable is missing: {installed_exe}"}
    if not uninstaller.is_file():
        return {
            "ok": False,
            "message": "This copy was not installed with ORI Setup. Install ORI-Setup.exe once before using in-app updates.",
        }
    if not installer.is_file() or installer.suffix.lower() != ".exe":
        return {"ok": False, "message": "The downloaded ORI Setup executable is missing or invalid."}

    bundled_root = Path(getattr(sys, "_MEIPASS", install_dir)).resolve()
    helper_source = bundled_root / "core" / "install_update.ps1"
    if not helper_source.is_file():
        helper_source = Path(__file__).resolve().with_name("install_update.ps1")

    state_dir = _local_app_data() / "ORI" / "updates" / "install-helper"
    log_name = f"install-{APP_VERSION}-{os.getpid()}.log"
    rollback_dir = state_dir / f"rollback-{APP_VERSION}-{os.getpid()}"
    ok, detail, log_file = _launch_detached_helper(
        helper_source=helper_source,
        state_dir=state_dir,
        script_prefix="install-update",
        log_name=log_name,
        arguments=[
            "-AppPid", str(os.getpid()),
            "-InstallerPath", str(installer),
            "-InstallDir", str(install_dir),
            "-ExpectedVersion", target_version,
            "-LogPath", str(log_file := (state_dir / log_name)),
            "-RollbackDir", str(rollback_dir),
        ],
        cwd=install_dir,
    )
    if not ok:
        return {"ok": False, "message": f"Could not launch the update installer: {detail}"}
    return {
        "ok": True,
        "log_file": str(log_file or ""),
        "message": (
            f"The verified ORI {target_version} Setup installer has started. ORI will close; "
            "the helper will verify the exact installed version, executable path and new process "
            f"before reporting success. The previous build is restored on failure. Log: {log_file}"
        ),
    }


def schedule_uninstall() -> dict[str, Any]:
    """Start the graphical ORI uninstall wizard after the current process exits."""
    if platform_name() != "Windows" or not getattr(sys, "frozen", False):
        return {"ok": False, "message": "The Settings uninstall action requires the installed Windows build."}

    install_dir = Path(sys.executable).resolve().parent
    uninstaller = install_dir / "unins000.exe"
    if not uninstaller.is_file():
        return {"ok": False, "message": "The ORI uninstaller is missing. Reinstall with ORI-Setup.exe first."}

    bundled_root = Path(getattr(sys, "_MEIPASS", install_dir)).resolve()
    helper_source = bundled_root / "core" / "uninstall_launcher.ps1"
    if not helper_source.is_file():
        helper_source = Path(__file__).resolve().with_name("uninstall_launcher.ps1")

    state_dir = _local_app_data() / "ORI" / "updates" / "install-helper"
    log_name = f"uninstall-{APP_VERSION}-{os.getpid()}.log"
    ok, detail, log_file = _launch_detached_helper(
        helper_source=helper_source,
        state_dir=state_dir,
        script_prefix="uninstall",
        log_name=log_name,
        arguments=[
            "-AppPid", str(os.getpid()),
            "-UninstallerPath", str(uninstaller),
            "-LogPath", str(state_dir / log_name),
        ],
        cwd=install_dir,
    )
    if not ok:
        return {"ok": False, "message": f"Could not launch the ORI uninstaller: {detail}"}
    return {
        "ok": True,
        "log_file": str(log_file or ""),
        "message": f"The ORI uninstall wizard will open after the application closes. Log: {log_file}",
    }


def platform_name() -> str:
    import platform
    return platform.system()
