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
from typing import Any, Callable

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



def _download(
    url: str,
    target: Path,
    timeout: float = 45.0,
    progress_callback: Callable[[dict[str, Any]], None] | None = None,
    max_bytes: int = _MAX_DOWNLOAD,
) -> None:
    """Download atomically and report real byte counts to the Settings progress bar."""
    if not str(url or "").startswith("https://"):
        raise ValueError("Release asset URL must use HTTPS.")
    target.parent.mkdir(parents=True, exist_ok=True)
    part = target.with_name(target.name + ".part")
    part.unlink(missing_ok=True)
    total = 0
    expected = 0
    try:
        with requests.get(
            url,
            stream=True,
            timeout=(8, max(5.0, min(float(timeout), 90.0))),
            headers={"Accept": "application/octet-stream"},
        ) as response:
            response.raise_for_status()
            try:
                expected = int(response.headers.get("Content-Length", 0) or 0)
            except (TypeError, ValueError):
                expected = 0
            if expected > max_bytes:
                raise ValueError("ORI Setup exceeds the 700 MB safety limit.")
            with part.open("wb") as output:
                for chunk in response.iter_content(1024 * 256):
                    if not chunk:
                        continue
                    total += len(chunk)
                    if total > max_bytes:
                        raise ValueError("ORI Setup exceeds the 700 MB safety limit.")
                    output.write(chunk)
                    if progress_callback is not None:
                        try:
                            progress_callback({
                                "stage": "download",
                                "downloaded_bytes": total,
                                "total_bytes": expected,
                                "percent": min(100, int(total * 100 / expected)) if expected else None,
                                "status": "Downloading",
                            })
                        except Exception:
                            pass
        if total <= 0 or not part.is_file():
            raise ValueError("The release server returned an empty installer file.")
        os.replace(part, target)
        if progress_callback is not None:
            try:
                progress_callback({
                    "stage": "download", "downloaded_bytes": total,
                    "total_bytes": expected or total, "percent": 100,
                    "status": "Download complete",
                })
            except Exception:
                pass
    except Exception:
        part.unlink(missing_ok=True)
        raise


def _sha256_file(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def download_latest_update(
    info: dict[str, Any] | None = None,
    progress_callback: Callable[[dict[str, Any]], None] | None = None,
) -> dict[str, Any]:
    """Download Setup, report actual progress and verify its SHA-256."""
    info = info or check_for_updates()
    if not info.get("ok") or not info.get("update_available"):
        return {"ok": False, "message": str(info.get("message") or "No update is available.")}
    asset, checksum = info.get("asset"), info.get("checksum_asset")
    if not isinstance(asset, dict) or not isinstance(checksum, dict):
        return {"ok": False, "message": "The release is missing the ORI Setup installer or SHA-256 checksum."}
    name = Path(str(asset.get("name") or "")).name
    if not _SETUP_RE.fullmatch(name):
        return {"ok": False, "message": "The release asset is not a versioned ORI Setup executable."}
    if str(checksum.get("name") or "") != name + ".sha256":
        return {"ok": False, "message": "The installer checksum sidecar does not match its file name."}
    urls = [str(asset.get("browser_download_url") or ""), str(checksum.get("browser_download_url") or "")]
    if any(not item.startswith("https://") for item in urls):
        return {"ok": False, "message": "Release asset URL must use HTTPS; nothing was downloaded."}
    safe_version = re.sub(r"[^A-Za-z0-9_.-]", "_", str(info.get("tag_name") or info.get("latest_version") or "latest"))
    folder = _local_app_data() / "ORI" / "updates" / safe_version
    installer_path = folder / name
    checksum_path = folder / (name + ".sha256")
    try:
        _download(urls[1], checksum_path, max_bytes=64 * 1024)
        match = re.search(r"\b([a-fA-F0-9]{64})\b", checksum_path.read_text(encoding="utf-8", errors="replace"))
        if not match:
            raise ValueError("The checksum file does not contain a SHA-256 digest.")
        expected = match.group(1).lower()
        if installer_path.is_file() and _sha256_file(installer_path) == expected:
            digest = expected
            if progress_callback is not None:
                progress_callback({
                    "stage": "verified", "downloaded_bytes": installer_path.stat().st_size,
                    "total_bytes": installer_path.stat().st_size, "percent": 100,
                    "status": "SHA-256 verified",
                })
            return {
                "ok": True, "version": info.get("latest_version"),
                "installer_path": str(installer_path), "sha256": digest,
                "message": "The verified installer is already downloaded.",
            }
        installer_path.unlink(missing_ok=True)
        _download(urls[0], installer_path, progress_callback=progress_callback)
        if progress_callback is not None:
            size = installer_path.stat().st_size
            progress_callback({
                "stage": "verify", "downloaded_bytes": size, "total_bytes": size,
                "percent": 100, "status": "Verifying SHA-256",
            })
        digest = _sha256_file(installer_path)
        if digest != expected:
            installer_path.unlink(missing_ok=True)
            raise ValueError("Installer SHA-256 verification failed; the file was discarded.")
        if progress_callback is not None:
            size = installer_path.stat().st_size
            progress_callback({
                "stage": "verified", "downloaded_bytes": size, "total_bytes": size,
                "percent": 100, "status": "SHA-256 verified",
            })
        return {
            "ok": True, "version": info.get("latest_version"),
            "installer_path": str(installer_path), "sha256": digest,
            "message": f"ORI {info.get('latest_version')} Setup downloaded and verified.",
        }
    except Exception as exc:
        installer_path.unlink(missing_ok=True)
        installer_path.with_name(installer_path.name + ".part").unlink(missing_ok=True)
        return {"ok": False, "message": f"Update download/verification failed: {type(exc).__name__}: {exc}"}


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
            "-STA",
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
    expected_sha256: str | None = None,
) -> dict[str, Any]:
    """Open a visible Update Assistant for a verified Windows Setup installer."""
    if platform_name() != "Windows" or not getattr(sys, "frozen", False):
        return {"ok": False, "message": "Automatic installation is available only in the installed Windows release."}
    install_dir = Path(sys.executable).resolve().parent
    installed_exe = install_dir / "ORI.exe"
    uninstaller = install_dir / "unins000.exe"
    installer = Path(installer_path).expanduser().resolve()
    setup_match = _SETUP_RE.fullmatch(installer.name)
    target_version = str(expected_version or (setup_match.group(1) if setup_match else "")).strip()
    if not re.fullmatch(r"\d+\.\d+\.\d+", target_version):
        return {"ok": False, "message": "The downloaded installer does not contain a valid target ORI version."}
    if not setup_match or setup_match.group(1) != target_version:
        return {"ok": False, "message": "The target ORI version does not match the downloaded Setup filename."}
    if not installed_exe.is_file():
        return {"ok": False, "message": f"The installed ORI executable is missing: {installed_exe}"}
    if not uninstaller.is_file():
        return {"ok": False, "message": "This copy was not installed with ORI Setup. Install ORI-Setup.exe once before using in-app updates."}
    if not installer.is_file() or installer.suffix.lower() != ".exe":
        return {"ok": False, "message": "The downloaded ORI Setup executable is missing or invalid."}
    try:
        actual_digest = _sha256_file(installer).lower()
    except OSError as exc:
        return {"ok": False, "message": f"The downloaded installer could not be read: {exc}"}
    expected_digest = str(expected_sha256 or actual_digest).strip().lower()
    if not re.fullmatch(r"[a-f0-9]{64}", expected_digest) or actual_digest != expected_digest:
        return {"ok": False, "message": "The downloaded installer no longer matches its SHA-256 checksum. Download it again."}

    bundled_root = Path(getattr(sys, "_MEIPASS", install_dir)).resolve()
    assistant_source = bundled_root / "core" / "update_assistant.ps1"
    install_helper = bundled_root / "core" / "install_update.ps1"
    source_root = Path(__file__).resolve().parent
    if not assistant_source.is_file():
        assistant_source = source_root / "update_assistant.ps1"
    if not install_helper.is_file():
        install_helper = source_root / "install_update.ps1"
    if not assistant_source.is_file() or not install_helper.is_file():
        return {"ok": False, "message": "The ORI Update Assistant is missing from this build. Reinstall ORI before updating."}

    state_dir = _local_app_data() / "ORI" / "updates" / "install-helper"
    assistant_log = state_dir / f"update-assistant-{APP_VERSION}-{os.getpid()}.log"
    backend_log = state_dir / f"update-backend-{APP_VERSION}-{os.getpid()}.log"
    rollback_dir = state_dir / f"rollback-{APP_VERSION}-{os.getpid()}"
    persistent_install_helper = state_dir / f"install-update-{os.getpid()}.ps1"
    try:
        import shutil
        state_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(install_helper, persistent_install_helper)
    except OSError as exc:
        return {"ok": False, "message": f"Could not prepare the persistent install helper: {exc}"}
    ok, detail, log_file = _launch_detached_helper(
        helper_source=assistant_source,
        state_dir=state_dir,
        script_prefix="update-assistant",
        log_name=assistant_log.name,
        arguments=[
            "-AppPid", str(os.getpid()), "-InstallerPath", str(installer),
            "-InstallDir", str(install_dir), "-ExpectedVersion", target_version,
            "-ExpectedSha256", actual_digest, "-LogPath", str(assistant_log),
            "-RollbackDir", str(rollback_dir), "-InstallHelperPath", str(persistent_install_helper),
            "-BackendLogPath", str(backend_log),
        ],
        cwd=install_dir,
    )
    if not ok:
        return {"ok": False, "message": f"Could not launch the Update Assistant: {detail}"}
    return {
        "ok": True, "log_file": str(log_file or ""),
        "message": f"ORI Update Assistant opened for version {target_version}. It will show installation status and offer LAUNCH ORI after verification.",
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
