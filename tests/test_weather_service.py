import unittest
from unittest.mock import Mock, patch

from core import weather_service as weather


class WeatherServiceTests(unittest.TestCase):
    @patch("core.weather_service.requests.get")
    def test_ip_location_is_approximate_and_validated(self, get):
        resp = Mock()
        resp.json.return_value = {
            "latitude": 25.31, "longitude": 83.12,
            "city": "Varanasi", "region": "Uttar Pradesh", "country_name": "India",
        }
        get.return_value = resp
        loc = weather.resolve_approximate_ip_location()
        self.assertEqual(loc["city"], "Varanasi")
        self.assertEqual(loc["location_source"], "public-IP estimate")
        self.assertEqual(get.call_args.args[0], weather.IP_LOCATION_URL)

    @patch("core.weather_service.requests.get")
    def test_weather_payload_formats_current_data(self, get):
        resp = Mock()
        resp.json.return_value = {
            "current": {
                "temperature_2m": 29.1, "apparent_temperature": 32.0,
                "relative_humidity_2m": 61, "wind_speed_10m": 8.2,
                "weather_code": 2, "time": "2026-10-18T15:00",
            }
        }
        get.return_value = resp
        result = weather.fetch_current_weather({
            "latitude": 25.3, "longitude": 83.1, "city": "Varanasi",
            "region": "UP", "country": "India", "location_label": "Varanasi, UP, India",
            "location_source": "public-IP estimate",
        })
        self.assertEqual(result["temperature_c"], 29.1)
        self.assertEqual(result["condition"], "Partly cloudy")
        self.assertEqual(result["source"], "Open-Meteo")

    def test_invalid_coordinates_are_rejected(self):
        with self.assertRaises(ValueError):
            weather.fetch_current_weather({"latitude": 120, "longitude": 0})

    @patch("core.weather_service.requests.get")
    def test_empty_geocoding_result_is_clear_error(self, get):
        resp = Mock()
        resp.json.return_value = {"results": []}
        get.return_value = resp
        with self.assertRaisesRegex(ValueError, "No matching location"):
            weather.geocode_city("nonexistent area")


if __name__ == "__main__":
    unittest.main()
