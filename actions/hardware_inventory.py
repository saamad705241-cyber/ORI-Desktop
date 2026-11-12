"""Read-only hardware inventory for ORI's hardware-awareness tools.

This module deliberately excludes serial numbers, UUIDs, MAC addresses, product
keys, PnP device IDs and other machine identifiers. Optional providers fail
closed: missing hardware data is returned as null/empty instead of guessed.
"""
from __future__ import annotations

import json
import platform
from typing import Any

import psutil

from core.hardware_sensors import get_cpu_temperature

_GB = 1024 ** 3


def _text(value: Any) -> str | None:
    if value is None:
        return None
    value = str(value).strip()
    return value or None


def _number(value: Any) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return result if result >= 0 else None


def _gb(value: Any) -> float | None:
    number = _number(value)
    return round(number / _GB, 2) if number is not None else None


def _query(connection: Any, class_name: str) -> list[Any]:
    try:
        method = getattr(connection, class_name)
        return list(method() or [])
    except Exception:
        return []


def _record_value(record: Any, name: str) -> Any:
    try:
        return getattr(record, name, None)
    except Exception:
        return None


def _collect_wmi(connection: Any) -> dict[str, Any]:
    """Convert selected Win32 CIM classes into a privacy-conscious snapshot."""
    computers = _query(connection, "Win32_ComputerSystem")
    processors = _query(connection, "Win32_Processor")
    memory = _query(connection, "Win32_PhysicalMemory")
    graphics = _query(connection, "Win32_VideoController")
    boards = _query(connection, "Win32_BaseBoard")
    operating_systems = _query(connection, "Win32_OperatingSystem")
    disks = _query(connection, "Win32_DiskDrive")

    computer = computers[0] if computers else None
    processor_list = []
    for item in processors:
        processor_list.append({
            "name": _text(_record_value(item, "Name")),
            "physical_cores": _number(_record_value(item, "NumberOfCores")),
            "logical_processors": _number(_record_value(item, "NumberOfLogicalProcessors")),
            "max_clock_mhz": _number(_record_value(item, "MaxClockSpeed")),
            "current_clock_mhz": _number(_record_value(item, "CurrentClockSpeed")),
        })

    memory_modules = []
    for item in memory:
        capacity = _record_value(item, "Capacity")
        memory_modules.append({
            "locator": _text(_record_value(item, "DeviceLocator")),
            "bank": _text(_record_value(item, "BankLabel")),
            "capacity_gb": _gb(capacity),
            "manufacturer": _text(_record_value(item, "Manufacturer")),
            "speed_mhz": _number(_record_value(item, "Speed")),
            "configured_speed_mhz": _number(_record_value(item, "ConfiguredClockSpeed")),
            "form_factor": _number(_record_value(item, "FormFactor")),
        })

    gpu_list = []
    for item in graphics:
        # Win32_VideoController.AdapterRAM is a 32-bit field on many Windows
        # versions. Values at its ceiling are overflow markers, not VRAM sizes.
        adapter_ram = _number(_record_value(item, "AdapterRAM"))
        if adapter_ram is not None and adapter_ram >= 4294967295:
            adapter_ram = None
        gpu_list.append({
            "name": _text(_record_value(item, "Name")),
            "driver_version": _text(_record_value(item, "DriverVersion")),
            "video_processor": _text(_record_value(item, "VideoProcessor")),
            "memory_gb": round(adapter_ram / _GB, 2) if adapter_ram else None,
        })

    board = boards[0] if boards else None
    os_record = operating_systems[0] if operating_systems else None

    disk_list = []
    for item in disks:
        disk_list.append({
            "model": _text(_record_value(item, "Model")),
            "size_gb": _gb(_record_value(item, "Size")),
            "interface": _text(_record_value(item, "InterfaceType")),
            "media_type": _text(_record_value(item, "MediaType")),
        })

    installed_module_bytes = sum(
        _number(_record_value(item, "Capacity")) or 0 for item in memory
    )
    return {
        "system": {
            "manufacturer": _text(_record_value(computer, "Manufacturer")),
            "model": _text(_record_value(computer, "Model")),
            "family": _text(_record_value(computer, "SystemFamily")),
            "system_type": _text(_record_value(computer, "SystemType")),
            "wmi_total_memory_gb": _gb(_record_value(computer, "TotalPhysicalMemory")),
        },
        "processors": processor_list,
        "memory_modules": memory_modules,
        "installed_module_memory_gb": round(installed_module_bytes / _GB, 2) if installed_module_bytes else None,
        "graphics": gpu_list,
        "motherboard": {
            "manufacturer": _text(_record_value(board, "Manufacturer")),
            "model": _text(_record_value(board, "Product")),
        } if board else {"manufacturer": None, "model": None},
        "operating_system": {
            "name": _text(_record_value(os_record, "Caption")),
            "version": _text(_record_value(os_record, "Version")),
            "build": _text(_record_value(os_record, "BuildNumber")),
            "architecture": _text(_record_value(os_record, "OSArchitecture")),
        } if os_record else {},
        "physical_disks": disk_list,
        "wmi_available": bool(computers or processors or memory or graphics or boards or operating_systems or disks),
    }


def _get_wmi_connection() -> Any | None:
    if platform.system() != "Windows":
        return None
    try:
        import wmi  # type: ignore
        return wmi.WMI()
    except Exception:
        return None


def _collect_nvidia_metrics() -> list[dict[str, Any]]:
    """Read supported NVIDIA telemetry through NVML; unavailable sensors stay null."""
    try:
        import pynvml  # type: ignore
    except Exception:
        return []

    initialized = False
    devices: list[dict[str, Any]] = []
    try:
        pynvml.nvmlInit()
        initialized = True
        count = int(pynvml.nvmlDeviceGetCount())
        for index in range(count):
            handle = pynvml.nvmlDeviceGetHandleByIndex(index)
            raw_name = pynvml.nvmlDeviceGetName(handle)
            name = raw_name.decode("utf-8", "replace") if isinstance(raw_name, bytes) else str(raw_name)
            item: dict[str, Any] = {
                "name": name.strip() or None,
                "index": index,
                "memory_total_gb": None,
                "memory_used_gb": None,
                "gpu_percent": None,
                "memory_percent": None,
                "temperature_c": None,
            }
            try:
                memory = pynvml.nvmlDeviceGetMemoryInfo(handle)
                item["memory_total_gb"] = _gb(memory.total)
                item["memory_used_gb"] = _gb(memory.used)
                if memory.total:
                    item["memory_percent"] = round(memory.used * 100 / memory.total, 1)
            except Exception:
                pass
            try:
                utilisation = pynvml.nvmlDeviceGetUtilizationRates(handle)
                item["gpu_percent"] = round(float(utilisation.gpu), 1)
            except Exception:
                pass
            try:
                item["temperature_c"] = float(
                    pynvml.nvmlDeviceGetTemperature(handle, pynvml.NVML_TEMPERATURE_GPU)
                )
            except Exception:
                pass
            devices.append(item)
    except Exception:
        return []
    finally:
        if initialized:
            try:
                pynvml.nvmlShutdown()
            except Exception:
                pass
    return devices


def _collect_volumes() -> list[dict[str, Any]]:
    volumes = []
    try:
        partitions = psutil.disk_partitions(all=False)
    except Exception:
        return volumes
    for partition in partitions:
        try:
            usage = psutil.disk_usage(partition.mountpoint)
        except Exception:
            continue
        volumes.append({
            "mountpoint": partition.mountpoint,
            "filesystem": _text(partition.fstype),
            "total_gb": round(usage.total / _GB, 2),
            "used_gb": round(usage.used / _GB, 2),
            "free_gb": round(usage.free / _GB, 2),
            "usage_percent": round(usage.percent, 1),
        })
    return volumes


def get_hardware_inventory() -> dict[str, Any]:
    """Return the best available read-only hardware inventory for this computer."""
    wmi_connection = _get_wmi_connection()
    wmi_data = _collect_wmi(wmi_connection) if wmi_connection is not None else {
        "system": {},
        "processors": [],
        "memory_modules": [],
        "installed_module_memory_gb": None,
        "graphics": [],
        "motherboard": {"manufacturer": None, "model": None},
        "operating_system": {},
        "physical_disks": [],
        "wmi_available": False,
    }

    try:
        virtual_memory = psutil.virtual_memory()
        installed_memory_gb = wmi_data.get("installed_module_memory_gb")
        if installed_memory_gb is None:
            installed_memory_gb = wmi_data.get("system", {}).get("wmi_total_memory_gb")
        if installed_memory_gb is None:
            installed_memory_gb = round(virtual_memory.total / _GB, 2)
        memory_summary = {
            "installed_gb": installed_memory_gb,
            "available_gb": round(virtual_memory.available / _GB, 2),
            "used_gb": round(virtual_memory.used / _GB, 2),
            "usage_percent": round(virtual_memory.percent, 1),
            "modules": wmi_data.get("memory_modules", []),
        }
    except Exception:
        memory_summary = {
            "installed_gb": wmi_data.get("installed_module_memory_gb"),
            "available_gb": None,
            "used_gb": None,
            "usage_percent": None,
            "modules": wmi_data.get("memory_modules", []),
        }

    processors = wmi_data.get("processors", [])
    cpu_frequency = None
    try:
        frequency = psutil.cpu_freq()
        if frequency:
            cpu_frequency = {
                "current_mhz": round(float(frequency.current), 1),
                "min_mhz": round(float(frequency.min), 1),
                "max_mhz": round(float(frequency.max), 1),
            }
    except Exception:
        pass

    if not processors:
        processors = [{
            "name": _text(platform.processor()),
            "physical_cores": psutil.cpu_count(logical=False),
            "logical_processors": psutil.cpu_count(logical=True),
            "max_clock_mhz": cpu_frequency.get("max_mhz") if cpu_frequency else None,
            "current_clock_mhz": cpu_frequency.get("current_mhz") if cpu_frequency else None,
        }]

    cpu_thermal = get_cpu_temperature()
    nvidia_devices = _collect_nvidia_metrics()
    graphics = wmi_data.get("graphics", [])
    for metric in nvidia_devices:
        match = next(
            (item for item in graphics
             if item.get("name") and metric.get("name")
             and metric["name"].lower() in item["name"].lower()),
            None,
        )
        if match is not None:
            match.update({
                key: value for key, value in metric.items()
                if key != "name" and value is not None
            })
            if not match.get("memory_gb"):
                match["memory_gb"] = metric.get("memory_total_gb")
        else:
            graphics.append(metric)

    try:
        resolution = list(__import__("pyautogui").size())
    except Exception:
        resolution = None

    try:
        operating_system = wmi_data.get("operating_system") or {}
        if not operating_system:
            operating_system = {
                "name": platform.platform(),
                "version": platform.version(),
                "build": None,
                "architecture": platform.machine(),
            }
    except Exception:
        operating_system = {}

    return {
        "ok": True,
        "system": wmi_data.get("system") or {
            "manufacturer": None,
            "model": None,
            "family": None,
            "system_type": platform.machine(),
        },
        "processors": processors,
        "processor_frequency": cpu_frequency,
        "memory": memory_summary,
        "graphics": graphics,
        "cpu_thermal": cpu_thermal,
        "motherboard": wmi_data.get("motherboard"),
        "operating_system": operating_system,
        "storage": {
            "physical_disks": wmi_data.get("physical_disks", []),
            "volumes": _collect_volumes(),
        },
        "display": {"primary_resolution": resolution},
        "providers": {
            "windows_wmi": bool(wmi_data.get("wmi_available")),
            "nvidia_nvml": bool(nvidia_devices),
            "librehardwaremonitor_http": bool(cpu_thermal and cpu_thermal.get("provider") == "LibreHardwareMonitor HTTP"),
        },
        "privacy": {
            "serial_numbers_collected": False,
            "device_ids_collected": False,
            "mac_addresses_collected": False,
            "windows_product_keys_collected": False,
        },
    }


def hardware_inventory(parameters: dict | None = None, **_kwargs) -> str:
    """Action handler: provide a fresh inventory only when requested by the user."""
    return json.dumps(get_hardware_inventory(), ensure_ascii=False, indent=2)


TOOL = {
    "name": "hardware_inventory",
    "description": (
        "Read the computer's actual hardware specifications. Use when the user asks "
        "which laptop or PC they have, the exact manufacturer/model, processor name, "
        "CPU cores or threads, installed RAM and memory modules, graphics cards, "
        CPU temperature, GPU memory or temperature (when supported), motherboard, storage drives, 
        "Windows version/build, or screen resolution. This is read-only. Never guess "
        "a missing value; report null/unavailable when the hardware provider cannot "
        "read it. Serial numbers, MAC addresses, device IDs and product keys are not collected."
    ),
    "parameters": {"type": "OBJECT", "properties": {}, "required": []},
    "handler": hardware_inventory,
}
