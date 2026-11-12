import sys
from types import ModuleType, SimpleNamespace

from core import location_service


class FakeAsyncOperation:
    def __init__(self, result):
        self.result = result

    @property
    def completed(self):
        return None

    @completed.setter
    def completed(self, callback):
        callback(self, None)

    def get_results(self):
        return self.result


def _install_fake_winrt(monkeypatch, access, position=None):
    winrt = ModuleType("winrt")
    winrt.__path__ = []
    windows = ModuleType("winrt.windows")
    windows.__path__ = []
    devices = ModuleType("winrt.windows.devices")
    devices.__path__ = []
    geolocation = ModuleType("winrt.windows.devices.geolocation")
    geolocation.GeolocationAccessStatus = SimpleNamespace(ALLOWED=1, DENIED=2)

    class FakeGeolocator:
        @staticmethod
        def request_access_async():
            return FakeAsyncOperation(access)

        def get_geoposition_async(self):
            return FakeAsyncOperation(position)

    geolocation.Geolocator = FakeGeolocator
    monkeypatch.setitem(sys.modules, "winrt", winrt)
    monkeypatch.setitem(sys.modules, "winrt.windows", windows)
    monkeypatch.setitem(sys.modules, "winrt.windows.devices", devices)
    monkeypatch.setitem(sys.modules, "winrt.windows.devices.geolocation", geolocation)


def test_request_location_access_returns_coordinates_after_permission(monkeypatch):
    position = SimpleNamespace(
        coordinate=SimpleNamespace(
            point=SimpleNamespace(
                position=SimpleNamespace(latitude=28.6139, longitude=77.2090)
            ),
            accuracy=25.0,
        )
    )
    _install_fake_winrt(monkeypatch, 1, position)
    monkeypatch.setattr(location_service.platform, "system", lambda: "Windows")
    received = []

    started = location_service.request_location_access(received.append)

    assert started is True
    assert received == [{
        "ok": True,
        "latitude": 28.6139,
        "longitude": 77.209,
        "accuracy_m": 25.0,
        "source": "Windows device location",
    }]


def test_request_location_access_reports_denied_permission(monkeypatch):
    _install_fake_winrt(monkeypatch, 2)
    monkeypatch.setattr(location_service.platform, "system", lambda: "Windows")
    received = []

    started = location_service.request_location_access(received.append)

    assert started is True
    assert received[0]["ok"] is False
    assert received[0]["reason"] == "denied"


def test_request_location_access_handles_non_windows(monkeypatch):
    monkeypatch.setattr(location_service.platform, "system", lambda: "Linux")
    received = []

    started = location_service.request_location_access(received.append)

    assert started is False
    assert received[0]["reason"] == "unsupported"
