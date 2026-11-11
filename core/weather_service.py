"""Explicit-opt-in approximate-location and current-weather helpers for ORI.

Approximate area resolution uses the public IP address only after the user
presses the enable button. It is not GPS and can be wrong (VPNs, carriers,
corporate networks). Weather is fetched from Open-Meteo and is a model-based
current estimate, not a personal-location or weather-station measurement.
"""
from __future__ import annotations

from typing import Any
import requests

IP_LOCATION_URL = "https://ipapi.co/json/"
WEATHER_URL = "https://api.open-meteo.com/v1/forecast"
GEOCODING_URL = "https://geocoding-api.open-meteo.com/v1/search"
USER_AGENT = "ORI-Desktop-Assistant/3.1 (weather feature; user opt-in)"
TIMEOUT_SECONDS = 6

WEATHER_CODES = {
    0: "Clear sky", 1: "Mainly clear", 2: "Partly cloudy", 3: "Overcast",
    45: "Fog", 48: "Depositing rime fog", 51: "Light drizzle",
    53: "Moderate drizzle", 55: "Dense drizzle", 56: "Freezing drizzle",
    57: "Dense freezing drizzle", 61: "Slight rain", 63: "Moderate rain",
    65: "Heavy rain", 66: "Freezing rain", 67: "Heavy freezing rain",
    71: "Slight snow", 73: "Moderate snow", 75: "Heavy snow",
    77: "Snow grains", 80: "Rain showers", 81: "Moderate rain showers",
    82: "Violent rain showers", 85: "Snow showers", 86: "Heavy snow showers",
    95: "Thunderstorm", 96: "Thunderstorm with hail", 99: "Thunderstorm with heavy hail",
}


def _valid_coordinates(latitude: Any, longitude: Any) -> tuple[float, float]:
    try:
        lat, lon = float(latitude), float(longitude)
    except (TypeError, ValueError) as exc:
        raise ValueError("Location coordinates are missing or invalid.") from exc
    if not (-90 <= lat <= 90 and -180 <= lon <= 180):
        raise ValueError("Location coordinates are outside valid ranges.")
    return lat, lon


def resolve_approximate_ip_location() -> dict[str, Any]:
    """Resolve a coarse area from the network's public IP; caller must opt in."""
    response = requests.get(
        IP_LOCATION_URL,
        timeout=TIMEOUT_SECONDS,
        headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
    )
    response.raise_for_status()
    data = response.json()
    lat, lon = _valid_coordinates(data.get("latitude"), data.get("longitude"))
    city = str(data.get("city") or "Nearby area").strip()
    region = str(data.get("region") or "").strip()
    country = str(data.get("country_name") or data.get("country") or "").strip()
    return {
        "latitude": lat,
        "longitude": lon,
        "city": city,
        "region": region,
        "country": country,
        "location_source": "public-IP estimate",
        "location_label": ", ".join(part for part in (city, region, country) if part),
    }


def geocode_city(city_query: str) -> dict[str, Any]:
    """Resolve a user-entered city name through Open-Meteo geocoding."""
    query = (city_query or "").strip()
    if len(query) < 2:
        raise ValueError("Enter a city or area name with at least two characters.")
    response = requests.get(
        GEOCODING_URL,
        params={"name": query, "count": 5, "language": "en", "format": "json"},
        timeout=TIMEOUT_SECONDS,
        headers={"User-Agent": USER_AGENT},
    )
    response.raise_for_status()
    results = response.json().get("results") or []
    if not results:
        raise ValueError(f"No matching location found for '{query}'. Try a nearby city.")
    # Prefer an exact case-insensitive display-name match; otherwise first result.
    result = next((r for r in results if str(r.get("name", "")).casefold() == query.casefold()), results[0])
    lat, lon = _valid_coordinates(result.get("latitude"), result.get("longitude"))
    city = str(result.get("name") or query).strip()
    region = str(result.get("admin1") or "").strip()
    country = str(result.get("country") or "").strip()
    return {
        "latitude": lat,
        "longitude": lon,
        "city": city,
        "region": region,
        "country": country,
        "location_source": "user-entered area",
        "location_label": ", ".join(part for part in (city, region, country) if part),
    }


def fetch_current_weather(location: dict[str, Any]) -> dict[str, Any]:
    """Fetch current model-based conditions for a stored, consented location."""
    lat, lon = _valid_coordinates(location.get("latitude"), location.get("longitude"))
    response = requests.get(
        WEATHER_URL,
        params={
            "latitude": lat,
            "longitude": lon,
            "current": "temperature_2m,relative_humidity_2m,apparent_temperature,weather_code,wind_speed_10m",
            "timezone": "auto",
        },
        timeout=TIMEOUT_SECONDS,
        headers={"User-Agent": USER_AGENT},
    )
    response.raise_for_status()
    payload = response.json()
    current = payload.get("current") or {}
    if current.get("temperature_2m") is None:
        raise RuntimeError("Weather provider did not return a current temperature.")
    label = str(location.get("location_label") or location.get("city") or "Selected area")
    code = current.get("weather_code")
    try:
        condition = WEATHER_CODES.get(int(code), "Current conditions")
    except (TypeError, ValueError):
        condition = "Current conditions"
    return {
        "latitude": lat,
        "longitude": lon,
        "city": str(location.get("city") or "Nearby area"),
        "region": str(location.get("region") or ""),
        "country": str(location.get("country") or ""),
        "location_label": label,
        "location_source": str(location.get("location_source") or "saved area"),
        "temperature_c": float(current["temperature_2m"]),
        "apparent_temperature_c": _as_optional_float(current.get("apparent_temperature")),
        "relative_humidity": _as_optional_float(current.get("relative_humidity_2m")),
        "wind_speed_kmh": _as_optional_float(current.get("wind_speed_10m")),
        "weather_code": code,
        "condition": condition,
        "observed_at": str(current.get("time") or ""),
        "source": "Open-Meteo",
    }


def _as_optional_float(value: Any) -> float | None:
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def get_current_weather_by_approximate_ip() -> dict[str, Any]:
    """Resolve approximate public-IP area and fetch weather (explicit opt-in only)."""
    location = resolve_approximate_ip_location()
    return fetch_current_weather(location)
