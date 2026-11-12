"""Shared, truthful CPU-temperature readings for ORI.

LibreHardwareMonitor 0.9.5+ no longer exposes its historical WMI provider.
Its local HTTP JSON endpoint is therefore the primary Windows source.
"""
from __future__ import annotations

import json
import re
import urllib.request
from typing import Any

LHM_DATA_URL = "http://127.0.0.1:8085/data.json"
HTTP_TIMEOUT_SECONDS = 0.8
_TEMP_RE = re.compile(r"[-+]?\d+(?:[.,]\d+)?")


def _number(value: Any) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError, OverflowError):
        match = _TEMP_RE.search(str(value))
        if not match:
            return None
        try:
            parsed = float(match.group(0).replace(",", "."))
        except (TypeError, ValueError, OverflowError):
            return None
    if 0.0 < parsed < 125.0:
        return round(parsed, 1)
    return None


def _has_cpu_hint(parts: list[str]) -> bool:
    context = " ".join(parts).casefold()
    return any(token in context for token in (
        "cpu", "processor", "ryzen", "amdcpu", "intelcpu", "intel core",
    ))


def _is_gpu_context(parts: list[str], cpu_context: bool) -> bool:
    context = " ".join(parts).casefold()
    if any(token in context for token in (
        "nvidia", "geforce", "gpu", "graphics card", "video controller",
    )):
        return True
    # AMD APUs include "Radeon Graphics" in the CPU model name.
    if not cpu_context and any(token in context for token in ("radeon", "graphics")):
        return True
    return False


def parse_lhm_cpu_temperature(payload: Any) -> dict[str, Any] | None:
    """Find the best CPU package/core temperature in an LHM data.json tree."""
    candidates: list[tuple[int, float, str]] = []

    def walk(node: Any, parents: list[str]) -> None:
        if isinstance(node, list):
            for child in node:
                walk(child, parents)
            return
        if not isinstance(node, dict):
            return

        label = str(
            node.get("Text") or node.get("text") or node.get("Name")
            or node.get("name") or ""
        ).strip()
        identifier = str(node.get("id") or node.get("Identifier") or "")
        path_parts = parents + [label, identifier]
        sensor_type = str(
            node.get("Type") or node.get("type")
            or node.get("SensorType") or node.get("sensor_type") or ""
        ).casefold()

        if "temperature" in sensor_type:
            cpu_context = _has_cpu_hint(path_parts)
            if cpu_context and not _is_gpu_context(path_parts, cpu_context):
                value = _number(node.get("RawValue"))
                if value is None:
                    value = _number(node.get("Value"))
                if value is not None:
                    low_name = label.casefold()
                    if "package" in low_name:
                        priority = 100
                    elif "tctl" in low_name or "tdie" in low_name:
                        priority = 95
                    elif "die" in low_name:
                        priority = 90
                    elif "ccd" in low_name:
                        priority = 85
                    elif "core" in low_name:
                        priority = 80
                    elif "cpu" in low_name:
                        priority = 75
                    else:
                        priority = 50
                    candidates.append((priority, value, label or "CPU temperature"))

        for key in ("Children", "children"):
            children = node.get(key)
            if isinstance(children, (dict, list)):
                walk(children, path_parts)

    walk(payload, [])
    if not candidates:
        return None

    highest = max(item[0] for item in candidates)
    selected = [item for item in candidates if item[0] == highest]
    _priority, value, name = max(selected, key=lambda item: item[1])
    return {
        "temperature_c": value,
        "sensor": name,
        "provider": "LibreHardwareMonitor HTTP",
    }


def _read_lhm_http() -> dict[str, Any] | None:
    request = urllib.request.Request(
        LHM_DATA_URL,
        headers={"Accept": "application/json", "User-Agent": "ORI-Desktop/3.5.1"},
    )
    # Disable environment proxies: the only permitted destination is loopback.
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with opener.open(request, timeout=HTTP_TIMEOUT_SECONDS) as response:
            payload = json.loads(response.read(2_000_000).decode("utf-8"))
        return parse_lhm_cpu_temperature(payload)
    except Exception:
        return None


def _read_legacy_wmi() -> dict[str, Any] | None:
    """Compatibility path for older Libre/OpenHardwareMonitor installations."""
    try:
        import platform
        if platform.system() != "Windows":
            return None
        import wmi  # type: ignore
    except Exception:
        return None

    for namespace in (r"root\LibreHardwareMonitor", r"root\OpenHardwareMonitor"):
        try:
            connection = wmi.WMI(namespace=namespace)
            sensors = connection.Sensor(SensorType="Temperature")
        except Exception:
            continue
        candidates: list[tuple[int, float, str]] = []
        for sensor in sensors:
            name = str(getattr(sensor, "Name", "") or "")
            parent = str(getattr(sensor, "Parent", "") or "")
            hardware = str(getattr(sensor, "HardwareType", "") or "")
            parts = [name, parent, hardware]
            cpu_context = _has_cpu_hint(parts)
            if not cpu_context or _is_gpu_context(parts, cpu_context):
                continue
            value = _number(getattr(sensor, "Value", None))
            if value is None:
                continue
            lower = name.casefold()
            priority = 100 if "package" in lower else (
                95 if "tctl" in lower or "tdie" in lower else
                85 if "ccd" in lower else
                80 if "core" in lower else 50
            )
            candidates.append((priority, value, name or "CPU temperature"))
        if candidates:
            best = max(candidates, key=lambda item: (item[0], item[1]))
            return {
                "temperature_c": best[1],
                "sensor": best[2],
                "provider": "LibreHardwareMonitor WMI",
            }
    return None


def _read_psutil() -> dict[str, Any] | None:
    try:
        import psutil
        temperatures = psutil.sensors_temperatures()
    except Exception:
        return None

    for group in ("k10temp", "zenpower", "coretemp", "cpu_thermal", "cpu-thermal"):
        entries = temperatures.get(group) or []
        values = [
            (value, str(getattr(entry, "label", "") or group))
            for entry in entries
            if (value := _number(getattr(entry, "current", None))) is not None
        ]
        if values:
            value, label = max(values, key=lambda item: item[0])
            return {
                "temperature_c": value,
                "sensor": label,
                "provider": "psutil",
            }
    return None


def get_cpu_temperature() -> dict[str, Any] | None:
    """Return a verified CPU thermal reading, or None when no CPU sensor exists."""
    return _read_lhm_http() or _read_legacy_wmi() or _read_psutil()
