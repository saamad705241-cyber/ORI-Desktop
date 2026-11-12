from types import SimpleNamespace

from actions import hardware_inventory as inventory


class FakeWMI:
    def Win32_ComputerSystem(self):
        return [SimpleNamespace(
            Manufacturer="ASUS",
            Model="TUF Gaming A16 FA607NUQ",
            SystemFamily="TUF Gaming",
            SystemType="x64-based PC",
            TotalPhysicalMemory=16 * 1024**3,
        )]

    def Win32_Processor(self):
        return [SimpleNamespace(
            Name="AMD Ryzen 7 170 with Radeon Graphics",
            NumberOfCores=8,
            NumberOfLogicalProcessors=16,
            MaxClockSpeed=5200,
            CurrentClockSpeed=3000,
        )]

    def Win32_PhysicalMemory(self):
        return [SimpleNamespace(
            DeviceLocator="DIMM 0",
            BankLabel="BANK 0",
            Capacity=16 * 1024**3,
            Manufacturer="Micron Technology",
            Speed=5600,
            ConfiguredClockSpeed=5600,
            FormFactor=12,
        )]

    def Win32_VideoController(self):
        return [
            SimpleNamespace(
                Name="AMD Radeon(TM) Graphics",
                DriverVersion="32.0.21036.4001",
                VideoProcessor="AMD Radeon Graphics",
                AdapterRAM=512 * 1024**2,
            ),
            SimpleNamespace(
                Name="NVIDIA GeForce RTX 4050 Laptop GPU",
                DriverVersion="32.0.15.9162",
                VideoProcessor="GeForce RTX",
                AdapterRAM=4294967295,
            ),
        ]

    def Win32_BaseBoard(self):
        return [SimpleNamespace(
            Manufacturer="ASUSTeK COMPUTER INC.",
            Product="FA607NUQ",
        )]

    def Win32_OperatingSystem(self):
        return [SimpleNamespace(
            Caption="Microsoft Windows 11 Home Single Language",
            Version="10.0.26300",
            BuildNumber="26300",
            OSArchitecture="64-bit",
        )]

    def Win32_DiskDrive(self):
        return [SimpleNamespace(
            Model="KBG60ZNV512G KIOXIA",
            Size=512_110_190_592,
            InterfaceType="SCSI",
            MediaType="Fixed hard disk media",
            SerialNumber="DO-NOT-COLLECT",
        )]


def test_wmi_inventory_extracts_hardware_without_sensitive_identifiers():
    data = inventory._collect_wmi(FakeWMI())

    assert data["system"]["manufacturer"] == "ASUS"
    assert data["system"]["model"] == "TUF Gaming A16 FA607NUQ"
    assert data["processors"][0]["physical_cores"] == 8
    assert data["processors"][0]["logical_processors"] == 16
    assert data["memory_modules"][0]["capacity_gb"] == 16
    assert data["memory_modules"][0]["manufacturer"] == "Micron Technology"
    assert data["installed_module_memory_gb"] == 16
    assert len(data["graphics"]) == 2
    assert data["graphics"][1]["name"] == "NVIDIA GeForce RTX 4050 Laptop GPU"
    assert data["graphics"][1]["memory_gb"] is None
    assert data["motherboard"]["model"] == "FA607NUQ"
    assert data["operating_system"]["build"] == "26300"
    assert data["physical_disks"][0]["model"] == "KBG60ZNV512G KIOXIA"
    assert "SerialNumber" not in str(data)
    assert data["wmi_available"] is True


def test_wmi_collection_tolerates_missing_or_broken_classes():
    class PartialWMI:
        def Win32_ComputerSystem(self):
            raise RuntimeError("WMI unavailable")

        def Win32_Processor(self):
            return []

    data = inventory._collect_wmi(PartialWMI())

    assert data["system"]["model"] is None
    assert data["processors"] == []
    assert data["graphics"] == []
    assert data["physical_disks"] == []
    assert data["wmi_available"] is False


def test_inventory_falls_back_when_wmi_is_unavailable(monkeypatch):
    monkeypatch.setattr(inventory, "_get_wmi_connection", lambda: None)
    monkeypatch.setattr(inventory, "_collect_nvidia_metrics", lambda: [])
    monkeypatch.setattr(inventory, "_collect_volumes", lambda: [])

    data = inventory.get_hardware_inventory()

    assert data["ok"] is True
    assert data["providers"]["windows_wmi"] is False
    assert data["memory"]["installed_gb"] is not None
    assert data["memory"]["usage_percent"] is not None
    assert isinstance(data["processors"], list)
    assert isinstance(data["graphics"], list)
    assert data["privacy"]["serial_numbers_collected"] is False


def test_nvidia_metrics_are_merged_into_matching_graphics_card(monkeypatch):
    monkeypatch.setattr(inventory, "_get_wmi_connection", lambda: FakeWMI())
    monkeypatch.setattr(inventory, "_collect_nvidia_metrics", lambda: [{
        "name": "NVIDIA GeForce RTX 4050 Laptop GPU",
        "index": 0,
        "memory_total_gb": 6.0,
        "memory_used_gb": 1.5,
        "gpu_percent": 23.0,
        "memory_percent": 25.0,
        "temperature_c": 45.0,
    }])
    monkeypatch.setattr(inventory, "_collect_volumes", lambda: [])

    data = inventory.get_hardware_inventory()
    nvidia = next(item for item in data["graphics"] if item["name"].startswith("NVIDIA"))

    assert nvidia["gpu_percent"] == 23.0
    assert nvidia["memory_total_gb"] == 6.0
    assert nvidia["temperature_c"] == 45.0


def test_hardware_inventory_action_returns_json():
    import json

    data = json.loads(inventory.hardware_inventory({}))
    assert data["ok"] is True
    assert "system" in data
    assert "processors" in data
    assert "memory" in data
    assert "graphics" in data
    assert "cpu_thermal" in data
    assert "storage" in data
