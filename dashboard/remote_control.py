"""Authenticated, allow-listed local desktop controls for the ORI phone remote.

The mobile dashboard never sends arbitrary Python or shell commands.  It sends
small, validated pointer/key/media actions through this module.
"""
from __future__ import annotations

from typing import Any


_ALLOWED_KEYS = {
    "esc", "enter", "tab", "space", "backspace", "delete",
    "up", "down", "left", "right", "home", "end", "pageup",
    "pagedown", "insert", "f5", "f11", "f2", "volumeup",
    "volumedown", "volumemute", "playpause", "nexttrack", "prevtrack",
}
_ALLOWED_HOTKEYS = {
    ("alt", "tab"),
    ("win", "d"),
    ("win", "e"),
    ("win", "i"),
    ("win", "l"),
    ("ctrl", "c"),
    ("ctrl", "v"),
    ("ctrl", "x"),
    ("ctrl", "z"),
    ("ctrl", "y"),
    ("ctrl", "s"),
    ("ctrl", "w"),
    ("ctrl", "shift", "esc"),
}
_ALLOWED_MEDIA = {
    "play_pause": "playpause",
    "next": "nexttrack",
    "previous": "prevtrack",
    "volume_up": "volumeup",
    "volume_down": "volumedown",
    "volume_mute": "volumemute",
}
_ALLOWED_SYSTEM = {"show_desktop", "switch_window", "open_explorer", "open_settings", "lock_pc"}


def _clamp_int(value: Any, low: int, high: int, default: int = 0) -> int:
    try:
        return max(low, min(high, int(round(float(value)))))
    except (TypeError, ValueError, OverflowError):
        return default


def execute_pointer_action(payload: dict[str, Any]) -> dict[str, Any]:
    """Perform one small allow-listed input action. Intended to run off-loop."""
    if not isinstance(payload, dict):
        return {"ok": False, "error": "Invalid control message."}
    action = str(payload.get("action", "")).lower().strip()
    try:
        import pyautogui
    except Exception as exc:  # pragma: no cover - host-specific
        return {"ok": False, "error": f"Desktop input unavailable: {type(exc).__name__}."}

    try:
        if action == "move":
            dx = _clamp_int(payload.get("dx"), -160, 160)
            dy = _clamp_int(payload.get("dy"), -160, 160)
            pyautogui.moveRel(dx, dy, duration=0, _pause=False)
            return {"ok": True}

        if action == "click":
            button = str(payload.get("button", "left")).lower()
            if button not in {"left", "right", "middle"}:
                return {"ok": False, "error": "Unsupported mouse button."}
            clicks = 2 if bool(payload.get("double", False)) else 1
            pyautogui.click(button=button, clicks=clicks, interval=0.08, _pause=False)
            return {"ok": True}

        if action == "scroll":
            amount = _clamp_int(payload.get("amount"), -12, 12)
            if amount:
                pyautogui.scroll(amount, _pause=False)
            return {"ok": True}

        if action == "press":
            key = str(payload.get("key", "")).lower().strip()
            if key not in _ALLOWED_KEYS:
                return {"ok": False, "error": "This key is not enabled for remote input."}
            pyautogui.press(key, _pause=False)
            return {"ok": True}

        if action == "type_text":
            text = str(payload.get("text", ""))
            if not text or len(text) > 2000:
                return {"ok": False, "error": "Text must contain 1–2000 characters."}
            # Use the clipboard for Unicode text (including Hindi); restore the
            # user's previous clipboard shortly after the paste is issued.
            try:
                import pyperclip
                import time as _time
                previous = pyperclip.paste()
                pyperclip.copy(text)
                pyautogui.hotkey("ctrl", "v", _pause=False)
                _time.sleep(0.25)
                pyperclip.copy(previous)
                return {"ok": True, "characters": len(text)}
            except Exception:
                if text.isascii():
                    pyautogui.write(text, interval=0.008, _pause=False)
                    return {"ok": True, "characters": len(text)}
                return {"ok": False, "error": "Unicode typing requires the Windows clipboard service."}

        if action == "hotkey":
            keys = tuple(str(key).lower().strip() for key in payload.get("keys", []))
            if keys not in _ALLOWED_HOTKEYS:
                return {"ok": False, "error": "This key combination is not enabled remotely."}
            pyautogui.hotkey(*keys, _pause=False)
            return {"ok": True}

        if action == "media":
            name = str(payload.get("name", "")).lower().strip()
            key = _ALLOWED_MEDIA.get(name)
            if not key:
                return {"ok": False, "error": "Unsupported media action."}
            pyautogui.press(key, _pause=False)
            return {"ok": True}

        if action == "volume":
            percent = _clamp_int(payload.get("percent"), 0, 100)
            try:
                from ctypes import POINTER, cast
                from comtypes import CLSCTX_ALL
                from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume
                device = AudioUtilities.GetSpeakers()
                interface = device.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
                endpoint = cast(interface, POINTER(IAudioEndpointVolume))
                endpoint.SetMasterVolumeLevelScalar(percent / 100.0, None)
                return {"ok": True, "percent": percent}
            except Exception as exc:
                return {"ok": False, "error": f"PC volume slider unavailable: {type(exc).__name__}. Use volume up/down keys instead."}

        if action == "system":
            name = str(payload.get("name", "")).lower().strip()
            if name not in _ALLOWED_SYSTEM:
                return {"ok": False, "error": "Unsupported system action."}
            if name == "show_desktop":
                pyautogui.hotkey("win", "d", _pause=False)
            elif name == "switch_window":
                pyautogui.hotkey("alt", "tab", _pause=False)
            elif name == "open_explorer":
                pyautogui.hotkey("win", "e", _pause=False)
            elif name == "open_settings":
                pyautogui.hotkey("win", "i", _pause=False)
            elif name == "lock_pc":
                import ctypes
                if not hasattr(ctypes, "windll"):
                    return {"ok": False, "error": "PC lock is only available on Windows."}
                if not ctypes.windll.user32.LockWorkStation():
                    return {"ok": False, "error": "Windows refused the lock request."}
            return {"ok": True}

        return {"ok": False, "error": "Unknown remote input action."}
    except Exception as exc:  # pragma: no cover - host-specific
        return {"ok": False, "error": f"Input failed: {type(exc).__name__}."}


def capture_desktop_jpeg(max_width: int = 1440, quality: int = 62) -> bytes:
    """Capture the combined desktop and return a bounded JPEG frame."""
    import io
    import mss
    from PIL import Image

    with mss.mss() as capture:
        monitor = capture.monitors[0]
        shot = capture.grab(monitor)
        image = Image.frombytes("RGB", shot.size, shot.rgb)
    if image.width > max_width:
        height = max(1, round(image.height * max_width / image.width))
        image = image.resize((max_width, height), Image.Resampling.LANCZOS)
    out = io.BytesIO()
    image.save(out, format="JPEG", quality=max(35, min(82, int(quality))), optimize=True)
    return out.getvalue()


def validate_phone_screen_frame(data: bytes) -> bool:
    """Cheap JPEG/PNG signature validation before an in-memory frame is stored."""
    return bool(data) and len(data) <= 2 * 1024 * 1024 and (
        data.startswith(b"\xff\xd8\xff") or data.startswith(b"\x89PNG\r\n\x1a\n")
    )
