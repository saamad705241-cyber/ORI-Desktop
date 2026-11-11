import unittest
from unittest.mock import patch

from actions import current_weather


class CurrentWeatherActionTests(unittest.TestCase):
    @patch("actions.current_weather.load_api_keys", return_value={"weather_enabled": False})
    def test_local_weather_requires_opt_in(self, _load):
        result = current_weather.current_weather_action({})
        self.assertIn("weather is disabled", result.lower())

    @patch("actions.current_weather.fetch_current_weather")
    @patch("actions.current_weather.geocode_city")
    def test_explicit_city_returns_weather(self, geocode, fetch):
        geocode.return_value = {"latitude": 25.3, "longitude": 83.1, "city": "Varanasi", "location_label": "Varanasi, India"}
        fetch.return_value = {
            "location_label": "Varanasi, India", "city": "Varanasi", "temperature_c": 30.4,
            "condition": "Partly cloudy", "apparent_temperature_c": 33.0,
            "relative_humidity": 55, "wind_speed_kmh": 10.0,
        }
        result = current_weather.current_weather_action({"city": "Varanasi"})
        self.assertIn("30.4°C", result)
        self.assertIn("Open-Meteo", result)
        geocode.assert_called_once_with("Varanasi")


if __name__ == "__main__":
    unittest.main()
