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
