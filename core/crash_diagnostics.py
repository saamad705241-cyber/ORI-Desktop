"""Persistent, privacy-conscious diagnostics for fatal ORI runtime failures.

The log is stored in the user's local ORI data directory, never beside the
installed program, so it survives updates and can be attached to a bug report.
"""
from __future__ import annotations

import faulthandler
import sys
import threading
import traceback
from datetime import datetime
from pathlib import Path
from typing import TextIO

_LOG_HANDLE: TextIO | None = None
_LOG_PATH: Path | None = None
_LOG_LOCK = threading.RLock()
_HOOKS_INSTALLED = False


def _write_report(handle: TextIO, message: str, exc_info=None) -> None:
    timestamp = datetime.now().astimezone().isoformat(timespec="seconds")
    handle.write(f"\n[{timestamp}] {message}\n")
    if exc_info and exc_info[0] is not None:
        traceback.print_exception(exc_info[0], exc_info[1], exc_info[2], file=handle)
    handle.flush()


def log_diagnostic(message: str, exc_info=None) -> None:
    """Append a diagnostic record without ever allowing logging to crash ORI."""
    try:
        with _LOG_LOCK:
            if _LOG_HANDLE is not None:
                _write_report(_LOG_HANDLE, str(message), exc_info)
    except Exception:
        pass


def install_crash_diagnostics(log_dir: str | Path) -> Path | None:
    """Enable a durable Python and fatal-exception log; safe to call repeatedly."""
    global _LOG_HANDLE, _LOG_PATH, _HOOKS_INSTALLED

    try:
        with _LOG_LOCK:
            if _LOG_HANDLE is None:
                folder = Path(log_dir)
                folder.mkdir(parents=True, exist_ok=True)
                _LOG_PATH = folder / "ori-crash.log"
                _LOG_HANDLE = _LOG_PATH.open("a", encoding="utf-8", buffering=1)

            if not _HOOKS_INSTALLED:
                previous_sys_hook = sys.excepthook
                previous_thread_hook = threading.excepthook

                def _sys_hook(exc_type, exc_value, exc_tb):
                    log_diagnostic("Uncaught main-thread exception",
                                    (exc_type, exc_value, exc_tb))
                    previous_sys_hook(exc_type, exc_value, exc_tb)

                def _thread_hook(args):
                    log_diagnostic(
                        f"Uncaught exception in thread {getattr(args.thread, 'name', 'unknown')}",
                        (args.exc_type, args.exc_value, args.exc_traceback),
                    )
                    previous_thread_hook(args)

                sys.excepthook = _sys_hook
                threading.excepthook = _thread_hook
                try:
                    # CPython writes the fatal traceback directly to this file
                    # for supported native/fatal exceptions on Windows.
                    faulthandler.enable(file=_LOG_HANDLE, all_threads=True)
                except Exception as exc:
                    _write_report(_LOG_HANDLE, f"faulthandler could not be enabled: {exc}")
                _HOOKS_INSTALLED = True

        log_diagnostic("ORI diagnostic logging initialised")
        return _LOG_PATH
    except Exception:
        # A read-only disk or unusual profile must not block app startup.
        return None
