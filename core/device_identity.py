"""Read-only model and form-factor detection for the current computer.

Only manufacturer, marketed model and chassis class are exposed. No serial
numbers, host names, UUIDs, MAC addresses or product keys are queried.
"""
from __future__ import annotations

import platform
import subprocess
from pathlib import Path
from typing import Any

_GENERIC_MODELS = {
    "", "system product name", "system product", "to be filled by o.e.m.",
    "to be filled by oem", "default string", "unknown", "not applicable",
    "not specified", "system manufacturer",
}


def _clean(value: Any) -> str | None:
    if value is None:
        return None
    text = " ".join(str(value).strip().split())
    if text.casefold() in _GENERIC_MODELS:
        return None
    return text or None


def _records(connection: Any, method_name: str) -> list[Any]:
    try:
        return list(getattr(connection, method_name)() or [])
    except Exception:
        return []


def _windows_identity(connection: Any) -> dict[str, Any]:
    systems = _records(connection, "Win32_ComputerSystem")
    computer = systems[0] if systems else None
    manufacturer = _clean(getattr(computer, "Manufacturer", None)) if computer else None
    model = _clean(getattr(computer, "Model", None)) if computer else None
    raw_type = getattr(computer, "PCSystemType", None) if computer else None
    try:
        system_type = int(raw_type)
    except (TypeError, ValueError):
        system_type = 0

    if system_type == 2:
        form_factor = "LAPTOP"
    elif system_type in (1, 3):
        form_factor = "DESKTOP"
    else:
        lowered = (model or "").casefold()
        form_factor = (
            "LAPTOP"
            if any(word in lowered for word in ("laptop", "notebook", "ultrabook", "thinkpad"))
            else "PC"
        )

    name = " ".join(part for part in (manufacturer, model) if part)
    label = f"{form_factor} · {name}" if name else f"{form_factor} · model unavailable"
    return {
        "ok": bool(manufacturer or model),
        "form_factor": form_factor,
        "manufacturer": manufacturer,
        "model": model,
        "label": label,
        "source": "Windows WMI Win32_ComputerSystem",
    }


def _read_dmi(path: str) -> str | None:
    try:
        return _clean(Path(path).read_text(encoding="utf-8", errors="replace"))
    except Exception:
        return None


def _linux_identity() -> dict[str, Any]:
    manufacturer = _read_dmi("/sys/class/dmi/id/sys_vendor")
    model = _read_dmi("/sys/class/dmi/id/product_name")
    chassis = _read_dmi("/sys/class/dmi/id/chassis_type")
    try:
        chassis_code = int(chassis or "0")
    except ValueError:
        chassis_code = 0
    form_factor = "LAPTOP" if chassis_code in (8, 9, 10, 14) else (
        "DESKTOP" if chassis_code in (3, 4, 5, 6, 7) else "PC"
    )
    name = " ".join(part for part in (manufacturer, model) if part)
    label = f"{form_factor} · {name}" if name else f"{form_factor} · model unavailable"
    return {
        "ok": bool(manufacturer or model),
        "form_factor": form_factor,
        "manufacturer": manufacturer,
        "model": model,
        "label": label,
        "source": "Linux DMI",
    }


def _mac_identity() -> dict[str, Any]:
    model = None
    try:
        result = subprocess.run(
            ["sysctl", "-n", "hw.model"],
            capture_output=True, text=True, timeout=3.0, check=True,
        )
        model = _clean(result.stdout)
    except Exception:
        pass
    form_factor = "LAPTOP" if model and "macbook" in model.casefold() else "PC"
    label = f"{form_factor} · Apple {model}" if model else f"{form_factor} · model unavailable"
    return {
        "ok": bool(model),
        "form_factor": form_factor,
        "manufacturer": "Apple",
        "model": model,
        "label": label,
        "source": "macOS sysctl hw.model",
    }


def get_device_identity() -> dict[str, Any]:
    """Detect manufacturer, marketed model and laptop/desktop class."""
    system = platform.system()
    if system == "Windows":
        try:
            import wmi  # type: ignore
            return _windows_identity(wmi.WMI())
        except Exception:
            return {
                "ok": False, "form_factor": "PC", "manufacturer": None,
                "model": None, "label": "PC · model unavailable",
                "source": "Windows WMI unavailable",
            }
    if system == "Linux":
        return _linux_identity()
    if system == "Darwin":
        return _mac_identity()
    return {
        "ok": False, "form_factor": "PC", "manufacturer": None,
        "model": None, "label": "PC · model unavailable", "source": "unsupported platform",
    }
