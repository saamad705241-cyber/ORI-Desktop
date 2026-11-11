"""Fast, read-only overview of the current Windows desktop and system context."""
from __future__ import annotations

import platform
import time
from pathlib import Path
from typing import Any

import psutil


def _foreground_title() -> str | None:
    if platform.system() != "Windows":
        return None
    try:
        import ctypes
        user32 = ctypes.windll.user32
        hwnd = user32.GetForegroundWindow()
        if not hwnd:
            return None
        length = user32.GetWindowTextLengthW(hwnd)
        buffer = ctypes.create_unicode_buffer(max(1, length + 1))
        user32.GetWindowTextW(hwnd, buffer, len(buffer))
        title = buffer.value.strip()
        return title[:180] if title else None
    except Exception:
        return None


def _visible_windows(limit: int = 18) -> list[str]:
    if platform.system() != "Windows":
        return []
    try:
        import ctypes
        user32 = ctypes.windll.user32
        titles: list[str] = []
        enum_type = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)

        def callback(hwnd, _param):
            try:
                if not user32.IsWindowVisible(hwnd):
                    return True
                n = user32.GetWindowTextLengthW(hwnd)
                if n <= 0:
                    return True
                buf = ctypes.create_unicode_buffer(min(n + 1, 512))
                user32.GetWindowTextW(hwnd, buf, len(buf))
                title = buf.value.strip()
                if title and title not in titles:
                    titles.append(title[:140])
            except Exception:
                pass
            return len(titles) < limit

        user32.EnumWindows(enum_type(callback), 0)
        return titles[:limit]
    except Exception:
        return []


def get_desktop_overview() -> dict[str, Any]:
    try:
        mem = psutil.virtual_memory()
        disk = psutil.disk_usage(str(Path.home().anchor or Path.home()))
        cpu = psutil.cpu_percent(interval=0.15)
        boot = time.time() - psutil.boot_time()
        overview: dict[str, Any] = {
            "ok": True,
            "os": platform.platform(),
            "computer_name": platform.node(),
            "foreground_window": _foreground_title(),
            "visible_windows": _visible_windows(),
            "cpu_percent": round(cpu, 1),
            "ram_percent": round(mem.percent, 1),
            "ram_used_gb": round(mem.used / (1024 ** 3), 2),
            "ram_total_gb": round(mem.total / (1024 ** 3), 2),
            "disk_percent": round(disk.percent, 1),
            "disk_free_gb": round(disk.free / (1024 ** 3), 2),
            "desktop_path": str(Path.home() / "Desktop"),
            "home_path": str(Path.home()),
            "uptime_hours": round(boot / 3600, 1),
            "process_count": len(psutil.pids()),
        }
        try:
            import pyautogui
            overview["screen_resolution"] = list(pyautogui.size())
        except Exception:
            overview["screen_resolution"] = None
        return overview
    except Exception as exc:
        return {"ok": False, "error": f"Desktop overview failed: {type(exc).__name__}: {exc}"}


def desktop_overview(_parameters: dict | None = None, **_kwargs) -> str:
    import json
    return json.dumps(get_desktop_overview(), ensure_ascii=False, indent=2)


TOOL = {
    "name": "desktop_overview",
    "description": (
        "Read the actual current desktop context: foreground application, visible window titles, "
        "CPU/RAM/storage, uptime, resolution and desktop paths. Use for questions such as "
        "'tell me about my desktop', 'what is open', 'what is my PC doing' or 'check my computer'. "
        "This is a read-only snapshot; it does not capture screen contents. Use screen_process "
        "when the user asks what is visually on screen."
    ),
    "parameters": {"type": "OBJECT", "properties": {}, "required": []},
    "handler": desktop_overview,
}
