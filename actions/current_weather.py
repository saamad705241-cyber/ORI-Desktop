"""Current weather tool for ORI.

Uses a consented saved area when no city is supplied. A manually supplied city
is sent to Open-Meteo geocoding and current weather. No location is resolved
from public IP in this tool; that requires the user to enable it in Settings.
"""
from __future__ import annotations

from memory.config_manager import load_api_keys
from core.weather_service import geocode_city, fetch_current_weather


def current_weather_action(parameters: dict, player=None, session_memory=None) -> str:
    city = str((parameters or {}).get("city") or "").strip()
    try:
        if city:
            location = geocode_city(city)
        else:
            config = load_api_keys()
            if not config.get("weather_enabled"):
                return (
                    "Area weather is disabled. Enable approximate-area weather in Settings → "
                    "System & Weather, or ask for weather in a specific city."
                )
            try:
                lat = float(config["weather_latitude"])
                lon = float(config["weather_longitude"])
            except (KeyError, TypeError, ValueError):
                return "No saved weather area is available. Enable area weather or enter a city in Settings."
            location = {
                "latitude": lat,
                "longitude": lon,
                "city": config.get("weather_city") or "Selected area",
                "region": config.get("weather_region") or "",
                "country": config.get("weather_country") or "",
                "location_label": config.get("weather_location_label") or config.get("weather_city") or "Selected area",
                "location_source": config.get("weather_location_source") or "saved area",
            }
        weather = fetch_current_weather(location)
        city_label = weather.get("location_label") or weather.get("city") or "Selected area"
        answer = (
            f"Current weather estimate for {city_label}: {weather['temperature_c']:.1f}°C, "
            f"{weather.get('condition', 'current conditions')}"
        )
        feels = weather.get("apparent_temperature_c")
        humidity = weather.get("relative_humidity")
        wind = weather.get("wind_speed_kmh")
        if feels is not None:
            answer += f", feels like {feels:.1f}°C"
        if humidity is not None:
            answer += f", humidity {humidity:.0f}%"
        if wind is not None:
            answer += f", wind {wind:.1f} km/h"
        answer += ". This is an Open-Meteo model-based current estimate, not precise GPS or a guarantee of local station conditions."
        return answer
    except Exception as exc:
        return f"I couldn't retrieve current weather: {str(exc)[:260]}"


TOOL = {
    "name": "current_weather",
    "description": (
        "Returns current model-based weather conditions for a city, or for the user's saved area "
        "if approximate-area weather was explicitly enabled in ORI Settings. Does not activate location by itself."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "city": {
                "type": "STRING",
                "description": "Optional city/area name. Leave blank to use the saved weather area only if the user enabled it.",
            },
        },
        "required": [],
    },
    "handler": current_weather_action,
}
