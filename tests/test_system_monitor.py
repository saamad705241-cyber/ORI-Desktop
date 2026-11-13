from core import hardware_sensors
from actions import system_monitor


def test_voice_system_status_uses_shared_temperature_source(monkeypatch):
    monkeypatch.setattr(
        hardware_sensors,
        "get_cpu_temperature",
        lambda: {
            "temperature_c": 48.5,
            "sensor": "CPU Package",
            "provider": "test sensor",
        },
    )

    assert system_monitor._get_cpu_temp() == 48.5


def test_voice_system_status_reports_unavailable_when_shared_sensor_is_missing(monkeypatch):
    monkeypatch.setattr(hardware_sensors, "get_cpu_temperature", lambda: None)

    assert system_monitor._get_cpu_temp() == -1.0



def test_system_status_exposes_temperature_provider(monkeypatch):
    from types import SimpleNamespace

    monkeypatch.setattr(
        hardware_sensors,
        "get_cpu_temperature",
        lambda: {
            "temperature_c": 52.4,
            "sensor": "CPU Package",
            "provider": "LibreHardwareMonitor HTTP",
        },
    )
    monkeypatch.setattr(system_monitor.psutil, "cpu_percent", lambda interval=0.0: 12.5)
    monkeypatch.setattr(
        system_monitor.psutil,
        "virtual_memory",
        lambda: SimpleNamespace(percent=42.0, used=4 * 1024**3, total=8 * 1024**3),
    )
    monkeypatch.setattr(system_monitor.psutil, "boot_time", lambda: 1000.0)
    monkeypatch.setattr(system_monitor.psutil, "pids", lambda: [1, 2, 3])
    monkeypatch.setattr(system_monitor.time, "time", lambda: 4600.0)
    monkeypatch.setattr(system_monitor, "_get_gpu_usage", lambda: -1.0)

    result = system_monitor.get_system_status()

    assert result["cpu_temp_c"] == 52.4
    assert result["cpu_temp_source"] == "LibreHardwareMonitor HTTP"
