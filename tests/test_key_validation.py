import json
import unittest
from unittest.mock import patch

from core.key_validation import validate_google_api_key


class _Response:
    def __init__(self, payload, status=200):
        self.payload = payload
        self.status = status

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self, size=-1):
        return json.dumps(self.payload).encode("utf-8")


class _HTTPError:
    def __init__(self, code, payload):
        import urllib.error
        self.error = urllib.error.HTTPError(
            "https://example.invalid", code, "error", {}, None
        )
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self, size=-1):
        return json.dumps(self.payload).encode("utf-8")


class GeminiKeyValidationTests(unittest.TestCase):
    def test_rejects_empty_key_without_network(self):
        with patch("urllib.request.urlopen") as open_url:
            ok, message = validate_google_api_key("")
        self.assertFalse(ok)
        self.assertIn("Enter a Google", message)
        open_url.assert_not_called()

    def test_valid_key_requires_models_response(self):
        with patch("urllib.request.urlopen", return_value=_Response({"models": [{"name": "models/x"}]})):
            ok, message = validate_google_api_key("A" * 30)
        self.assertTrue(ok)
        self.assertIn("verified", message.lower())

    def test_api_key_is_sent_in_header_not_url(self):
        key = "C" * 30
        captured = {}

        def fake_open(request, timeout=0):
            captured["request"] = request
            captured["timeout"] = timeout
            return _Response({"models": [{"name": "models/gemini"}]})

        with patch("urllib.request.urlopen", side_effect=fake_open):
            ok, _ = validate_google_api_key(key)
        request = captured["request"]
        self.assertTrue(ok)
        self.assertEqual(request.get_header("X-goog-api-key"), key)
        self.assertNotIn(key, request.full_url)
        self.assertLessEqual(captured["timeout"], 15.0)

    def test_invalid_key_reports_google_rejection(self):
        response = _HTTPError(403, {"error": {"message": "API key not valid"}})
        with patch("urllib.request.urlopen", side_effect=response.error):
            # HTTPError.read is replaced by the real exception's file object,
            # so the public message remains safely generic.
            ok, message = validate_google_api_key("B" * 30)
        self.assertFalse(ok)
        self.assertIn("rejected", message.lower())


if __name__ == "__main__":
    unittest.main()
