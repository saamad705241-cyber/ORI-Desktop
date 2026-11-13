from types import SimpleNamespace

from core.device_identity import _windows_identity


class FakeWMI:
    def __init__(self, manufacturer, model, system_type):
        self._computer = SimpleNamespace(
            Manufacturer=manufacturer,
            Model=model,
            PCSystemType=system_type,
        )

    def Win32_ComputerSystem(self):
        return [self._computer]


def test_windows_identity_detects_laptop_and_exact_model():
    result = _windows_identity(
        FakeWMI("ASUS", "TUF Gaming A16 FA607NUQ", 2)
    )

    assert result["ok"] is True
    assert result["form_factor"] == "LAPTOP"
    assert result["manufacturer"] == "ASUS"
    assert result["model"] == "TUF Gaming A16 FA607NUQ"
    assert result["label"] == "LAPTOP · ASUS TUF Gaming A16 FA607NUQ"


def test_windows_identity_detects_desktop():
    result = _windows_identity(
        FakeWMI("Dell Inc.", "OptiPlex 7010", 1)
    )

    assert result["form_factor"] == "DESKTOP"
    assert result["model"] == "OptiPlex 7010"


def test_windows_identity_does_not_present_generic_model_as_real_model():
    result = _windows_identity(
        FakeWMI("To Be Filled By O.E.M.", "System Product Name", 2)
    )

    assert result["ok"] is False
    assert result["form_factor"] == "LAPTOP"
    assert result["model"] is None
    assert result["label"] == "LAPTOP · model unavailable"


def test_windows_identity_handles_missing_wmi_data():
    result = _windows_identity(SimpleNamespace(Win32_ComputerSystem=lambda: []))

    assert result["ok"] is False
    assert result["form_factor"] == "PC"
    assert result["model"] is None
