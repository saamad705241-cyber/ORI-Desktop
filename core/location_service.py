"""Windows device-location consent and one-shot coordinate access.

RequestAccessAsync is initiated by the foreground Qt UI thread. Completion
callbacks keep the Qt UI responsive and avoid blocking a GUI apartment.
"""
from __future__ import annotations

import math
import platform
from typing import Any, Callable


_PENDING_REQUESTS: dict[int, dict[str, Any]] = {}


def _position_payload(position: Any) -> dict[str, Any]:
    coordinate = position.coordinate
    point = coordinate.point.position
    latitude = float(point.latitude)
    longitude = float(point.longitude)
    if not (math.isfinite(latitude) and math.isfinite(longitude)):
        raise ValueError("Windows returned invalid location coordinates.")
    if not (-90 <= latitude <= 90 and -180 <= longitude <= 180):
        raise ValueError("Windows returned coordinates outside valid ranges.")
    accuracy = getattr(coordinate, "accuracy", None)
    try:
        accuracy_m = float(accuracy) if accuracy is not None else None
        if accuracy_m is not None and (not math.isfinite(accuracy_m) or accuracy_m < 0):
            accuracy_m = None
    except (TypeError, ValueError):
        accuracy_m = None
    return {
        "ok": True,
        "latitude": latitude,
        "longitude": longitude,
        "accuracy_m": accuracy_m,
        "source": "Windows device location",
    }


def request_location_access(callback: Callable[[dict[str, Any]], None]) -> bool:
    """Start permission and a one-shot position request from the foreground UI thread."""
    def deliver(result: dict[str, Any]) -> None:
        try:
            callback(result)
        except Exception:
            pass

    if platform.system() != "Windows":
        deliver({
            "ok": False,
            "reason": "unsupported",
            "error": "Windows device location is available only on Windows 10/11.",
        })
        return False

    try:
        from winrt.windows.devices.geolocation import GeolocationAccessStatus, Geolocator
        locator = Geolocator()
        access_operation = Geolocator.request_access_async()
    except Exception as exc:
        deliver({
            "ok": False,
            "reason": "unavailable",
            "error": f"Windows location API is unavailable: {type(exc).__name__}: {exc}",
        })
        return False

    request_id = id(access_operation)
    _PENDING_REQUESTS[request_id] = {
        "access_operation": access_operation,
        "locator": locator,
    }

    def position_completed(operation: Any, _status: Any) -> None:
        try:
            deliver(_position_payload(operation.get_results()))
        except Exception as exc:
            deliver({
                "ok": False,
                "reason": "position_unavailable",
                "error": f"Windows could not determine the device location: {type(exc).__name__}: {exc}",
            })
        finally:
            _PENDING_REQUESTS.pop(request_id, None)

    def access_completed(operation: Any, _status: Any) -> None:
        try:
            access = operation.get_results()
        except Exception as exc:
            _PENDING_REQUESTS.pop(request_id, None)
            deliver({
                "ok": False,
                "reason": "permission_error",
                "error": f"Windows location permission request failed: {type(exc).__name__}: {exc}",
            })
            return

        if access != GeolocationAccessStatus.ALLOWED:
            _PENDING_REQUESTS.pop(request_id, None)
            deliver({
                "ok": False,
                "reason": "denied",
                "error": "Windows location access was not allowed. Check Windows Settings > Privacy & security > Location.",
            })
            return

        try:
            position_operation = locator.get_geoposition_async()
            _PENDING_REQUESTS[request_id]["position_operation"] = position_operation
            position_operation.completed = position_completed
        except Exception as exc:
            _PENDING_REQUESTS.pop(request_id, None)
            deliver({
                "ok": False,
                "reason": "position_unavailable",
                "error": f"Could not start Windows location lookup: {type(exc).__name__}: {exc}",
            })

    try:
        access_operation.completed = access_completed
    except Exception as exc:
        _PENDING_REQUESTS.pop(request_id, None)
        deliver({
            "ok": False,
            "reason": "permission_error",
            "error": f"Could not register the Windows permission callback: {type(exc).__name__}: {exc}",
        })
        return False
    return True
