"""Read-only Windows Update diagnostics with a bounded timeout.

ORI never installs updates, changes update policy, or triggers a restart through
this tool. It only asks the Windows Update Agent for the pending-update list, or
opens the native Settings page when explicitly requested.
"""
from __future__ import annotations

import json
import platform
import subprocess
import time
from typing import Any

from actions.computer_control import is_action_cancelled


def _powershell(script: str, timeout: float = 28.0) -> subprocess.CompletedProcess:
    encoded = __import__("base64").b64encode(script.encode("utf-16le")).decode("ascii")
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0) if platform.system() == "Windows" else 0
    command = ["powershell.exe", "-NoProfile", "-NonInteractive", "-EncodedCommand", encoded]
    process = subprocess.Popen(
        command, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        text=True, encoding="utf-8", errors="replace", creationflags=flags,
    )
    deadline = time.monotonic() + max(1.0, float(timeout))
    while True:
        if is_action_cancelled():
            process.terminate()
            try:
                stdout, stderr = process.communicate(timeout=2.0)
            except subprocess.TimeoutExpired:
                process.kill()
                stdout, stderr = process.communicate()
            raise InterruptedError("Windows Update check was cancelled by the user.")
        try:
            stdout, stderr = process.communicate(timeout=0.15)
            return subprocess.CompletedProcess(command, process.returncode, stdout, stderr)
        except subprocess.TimeoutExpired:
            if time.monotonic() >= deadline:
                process.terminate()
                try:
                    process.communicate(timeout=2.0)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.communicate()
                raise subprocess.TimeoutExpired(command, timeout)


def check_windows_updates(timeout: float = 28.0) -> dict[str, Any]:
    """Return pending Windows updates or a useful bounded diagnostic."""
    if platform.system() != "Windows":
        return {"ok": False, "error": "Windows Update checks are only available on Windows."}
    script = r'''
$ErrorActionPreference = 'Stop'
try {
  $session = New-Object -ComObject Microsoft.Update.Session
  $searcher = $session.CreateUpdateSearcher()
  $result = $searcher.Search("IsInstalled=0 and IsHidden=0")
  $items = @()
  $limit = [Math]::Min([int]$result.Updates.Count, 40)
  for ($i = 0; $i -lt $limit; $i++) {
    $u = $result.Updates.Item($i)
    $items += [pscustomobject]@{
      title = [string]$u.Title
      downloaded = [bool]$u.IsDownloaded
      reboot_required = [bool]$u.RebootRequired
      kb = (@($u.KBArticleIDs) -join ', ')
    }
  }
  [pscustomobject]@{
    ok = $true
    pending_count = [int]$result.Updates.Count
    returned_count = [int]$items.Count
    updates = $items
    result_code = [int]$result.ResultCode
  } | ConvertTo-Json -Depth 5 -Compress
} catch {
  [pscustomobject]@{ ok = $false; error = [string]$_.Exception.Message } | ConvertTo-Json -Compress
}
'''
    try:
        completed = _powershell(script, timeout=timeout)
    except InterruptedError:
        return {"ok": False, "cancelled": True, "error": "Windows Update check was stopped by the user."}
    except subprocess.TimeoutExpired:
        return {
            "ok": False,
            "timeout": True,
            "error": f"Windows Update Agent did not respond within {int(timeout)} seconds. Open Windows Settings to continue manually.",
        }
    except FileNotFoundError:
        return {"ok": False, "error": "PowerShell was not found; Windows Update diagnostics are unavailable."}
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout or "Windows Update query failed.").strip()
        return {"ok": False, "error": detail[:500]}
    try:
        data = json.loads(completed.stdout.strip().splitlines()[-1])
        if not isinstance(data, dict):
            raise ValueError("Unexpected Windows Update response")
        return data
    except Exception as exc:
        return {
            "ok": False,
            "error": f"Could not parse Windows Update response: {type(exc).__name__}.",
            "detail": (completed.stdout or completed.stderr or "")[-500:],
        }


def open_windows_update_settings() -> dict[str, Any]:
    if platform.system() != "Windows":
        return {"ok": False, "error": "Windows Settings is only available on Windows."}
    try:
        import os
        os.startfile("ms-settings:windowsupdate")  # type: ignore[attr-defined]
        return {"ok": True, "message": "Opened Windows Update Settings."}
    except Exception as exc:
        return {"ok": False, "error": f"Could not open Windows Update Settings: {type(exc).__name__}: {exc}"}


def windows_update(parameters: dict, **_kwargs) -> str:
    action = str((parameters or {}).get("action", "check")).lower().strip()
    if action in {"check", "scan", "list"}:
        result = check_windows_updates()
    elif action in {"open", "settings"}:
        result = open_windows_update_settings()
    else:
        return "Supported actions are check and open. ORI does not install updates automatically."
    return json.dumps(result, ensure_ascii=False, indent=2)


TOOL = {
    "name": "windows_update",
    "description": (
        "Check Windows Update for pending updates or open the native Windows Update page. "
        "Use this instead of guessing or repeatedly clicking the Settings UI. The check is "
        "read-only, has a 28-second timeout, and never installs updates or restarts Windows."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {"type": "STRING", "description": "check | open"},
        },
        "required": ["action"],
    },
    "handler": windows_update,
}
