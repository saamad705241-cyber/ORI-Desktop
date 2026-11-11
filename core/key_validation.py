"""Google AI Studio API-key validation.

This performs a small, non-generative Models API request. It verifies that the
key is accepted by Google's Generative Language API without creating a chat,
starting audio, or consuming a model response.
"""
from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from typing import Any


def validate_google_api_key(api_key: str, timeout: float = 8.0) -> tuple[bool, str]:
    key = str(api_key or "").strip()
    if len(key) < 20:
        return False, "Enter a Google AI Studio API key."
    url = "https://generativelanguage.googleapis.com/v1beta/models?" + urllib.parse.urlencode(
        {"pageSize": 1}
    )
    request = urllib.request.Request(
        url,
        headers={
            "Accept": "application/json",
            "User-Agent": "ORI/3.3",
            "x-goog-api-key": key,
        },
        method="GET",
    )
    try:
        with urllib.request.urlopen(request, timeout=max(3.0, min(float(timeout), 15.0))) as response:
            payload: Any = json.loads(response.read(512_000).decode("utf-8"))
        if not isinstance(payload, dict):
            return False, "Google returned an unexpected response."
        models = payload.get("models")
        if not isinstance(models, list):
            return False, "Google did not return an available-model list."
        return True, "Google AI Studio key verified. ORI will choose a compatible Gemini model automatically."
    except urllib.error.HTTPError as exc:
        try:
            body = exc.read(8192).decode("utf-8", errors="replace")
            parsed = json.loads(body)
            message = str(parsed.get("error", {}).get("message", "")).strip()
        except Exception:
            message = ""
        if exc.code in (400, 401, 403):
            return False, message or "Google rejected this API key. Check that it was created in Google AI Studio."
        if exc.code == 429:
            return False, "Google rate limit reached while checking the key. Wait a little and retry."
        if exc.code in (500, 502, 503, 504):
            return False, f"Google service is temporarily unavailable (HTTP {exc.code}). Retry shortly."
        return False, message or f"Google API check failed (HTTP {exc.code})."
    except (TimeoutError, urllib.error.URLError, OSError) as exc:
        reason = getattr(exc, "reason", None) or exc
        return False, f"Could not reach Google AI Studio: {type(reason).__name__}."
    except Exception as exc:
        return False, f"Key verification failed: {type(exc).__name__}."


__all__ = ["validate_google_api_key"]
