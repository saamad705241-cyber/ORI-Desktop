from types import SimpleNamespace

from core import weather_service


def test_reverse_geocode_coordinates_uses_validated_coordinates(monkeypatch):
    calls = []

    class Response:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "address": {
                    "city": "Mughalsarai",
                    "state": "Uttar Pradesh",
                    "country": "India",
                }
            }

    def fake_get(url, **kwargs):
        calls.append((url, kwargs))
        return Response()

    monkeypatch.setattr(weather_service.requests, "get", fake_get)

    result = weather_service.reverse_geocode_coordinates(25.283, 83.12)

    assert result["city"] == "Mughalsarai"
    assert result["region"] == "Uttar Pradesh"
    assert result["country"] == "India"
    assert result["location_source"] == "Windows device location"
    assert calls[0][0] == "https://nominatim.openstreetmap.org/reverse"
    assert calls[0][1]["params"]["lat"] == 25.283
    assert calls[0][1]["params"]["lon"] == 83.12


def test_reverse_geocode_failure_keeps_safe_current_location_fallback(monkeypatch):
    def fake_get(*_args, **_kwargs):
        raise TimeoutError("reverse geocoder unavailable")

    monkeypatch.setattr(weather_service.requests, "get", fake_get)

    result = weather_service.reverse_geocode_coordinates(28.6139, 77.2090)

    assert result["city"] == "Current location"
    assert result["latitude"] == 28.6139
    assert result["longitude"] == 77.2090


def test_reverse_geocode_rejects_invalid_coordinates():
    try:
        weather_service.reverse_geocode_coordinates(120, 400)
    except ValueError as exc:
        assert "outside valid ranges" in str(exc)
    else:
        raise AssertionError("Invalid coordinates should not be accepted")
