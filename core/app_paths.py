"""Resolve ORI's writable per-user data paths independently of install files."""
from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

APP_NAME = "ORI"


def get_app_data_dir() -> Path:
    """Return the persistent data root.

    Source runs stay self-contained in the repository. Frozen Windows builds
    keep credentials, settings and memory under LocalAppData so installer
    updates and uninstalls never overwrite or remove them.
    """
    if not getattr(sys, "frozen", False):
        return Path(__file__).resolve().parent.parent

    if os.name == "nt":
        root = Path(os.environ.get("LOCALAPPDATA") or (Path.home() / "AppData" / "Local"))
    elif sys.platform == "darwin":
        root = Path.home() / "Library" / "Application Support"
    else:
        root = Path(os.environ.get("XDG_DATA_HOME") or (Path.home() / ".local" / "share"))

    data_dir = root / APP_NAME
    _migrate_legacy_data(Path(sys.executable).resolve().parent, data_dir)
    return data_dir


def _copy_file_once(source: Path, destination: Path) -> None:
    if not source.is_file() or destination.exists():
        return
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)


def _copy_tree_once(source: Path, destination: Path) -> None:
    if not source.is_dir():
        return
    for source_file in source.rglob("*"):
        if not source_file.is_file():
            continue
        relative = source_file.relative_to(source)
        destination_file = destination / relative
        if destination_file.exists():
            continue
        destination_file.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source_file, destination_file)


def _migrate_legacy_data(install_dir: Path, data_dir: Path) -> None:
    """Copy existing portable data once; never replace newer per-user data."""
    if install_dir.resolve() == data_dir.resolve():
        return

    _copy_file_once(
        install_dir / "config" / "api_keys.json",
        data_dir / "config" / "api_keys.json",
    )
    _copy_file_once(
        install_dir / "memory" / "long_term.json",
        data_dir / "memory" / "long_term.json",
    )

    # Preserve user-created material from older portable builds when present.
    for name in ("downloads", "screenshots", "logs"):
        _copy_tree_once(install_dir / name, data_dir / name)
    _copy_tree_once(
        install_dir / "config" / "certs",
        data_dir / "config" / "certs",
    )


def get_config_dir() -> Path:
    return get_app_data_dir() / "config"


def get_memory_dir() -> Path:
    return get_app_data_dir() / "memory"
