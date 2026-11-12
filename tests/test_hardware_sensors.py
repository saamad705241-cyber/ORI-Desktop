from core.hardware_sensors import parse_lhm_cpu_temperature


def test_lhm_json_prefers_cpu_package_and_ignores_gpu_temperatures():
    payload = {
        "Text": "Computer",
        "Children": [
            {
                "Text": "AMD Ryzen 7 170 with Radeon Graphics",
                "Type": "Hardware",
                "Children": [
                    {
                        "Text": "Temperatures",
                        "Children": [
                            {"Text": "CPU CCD #0 (Tdie)", "Type": "Temperature", "Value": "54.0 °C", "RawValue": 54.0},
                            {"Text": "CPU Package", "Type": "Temperature", "Value": "57.0 °C", "RawValue": 57.0},
                        ],
                    }
                ],
            },
            {
                "Text": "NVIDIA GeForce RTX 4050 Laptop GPU",
                "Type": "Hardware",
                "Children": [
                    {"Text": "GPU Core", "Type": "Temperature", "Value": "45.0 °C", "RawValue": 45.0}
                ],
            },
        ],
    }

    reading = parse_lhm_cpu_temperature(payload)

    assert reading == {
        "temperature_c": 57.0,
        "sensor": "CPU Package",
        "provider": "LibreHardwareMonitor HTTP",
    }


def test_lhm_json_accepts_cpu_sensor_value_without_raw_value():
    payload = {
        "Text": "AMD Ryzen 7 170",
        "Children": [
            {"Text": "Tctl/Tdie", "Type": "Temperature", "Value": "51.5 °C"}
        ],
    }

    reading = parse_lhm_cpu_temperature(payload)

    assert reading["temperature_c"] == 51.5
    assert reading["sensor"] == "Tctl/Tdie"


def test_lhm_json_does_not_guess_from_unrelated_or_gpu_sensors():
    payload = {
        "Text": "Computer",
        "Children": [
            {"Text": "NVIDIA GeForce RTX 4050", "Children": [
                {"Text": "GPU Core", "Type": "Temperature", "Value": "44 °C"}
            ]},
            {"Text": "Motherboard", "Children": [
                {"Text": "System", "Type": "Temperature", "Value": "38 °C"}
            ]},
        ],
    }

    assert parse_lhm_cpu_temperature(payload) is None


def test_lhm_json_rejects_out_of_range_sensor_values():
    payload = {
        "Text": "Intel Core i7 CPU",
        "Children": [
            {"Text": "CPU Package", "Type": "Temperature", "RawValue": 180.0}
        ],
    }

    assert parse_lhm_cpu_temperature(payload) is None
