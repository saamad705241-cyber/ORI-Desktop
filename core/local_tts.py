"""Speech output for ORI's local-first desktop runtime.

The default engine is the operating system's installed speech voice via
pyttsx3/SAPI on Windows, so text replies can be spoken without sending them to
a cloud service. An optional cloud/neural engine can be selected explicitly in
config/api_keys.json using ``tts_engine: "edgetts"``, ``"kokoro"``, or
``"elevenlabs"``; if it fails, ORI falls back to the system voice.
"""
from __future__ import annotations

import os
import re
import threading
from typing import Any

_SPEECH_LOCK = threading.Lock()


def clean_text_for_speech(text: str) -> str:
    """Remove formatting that sounds awkward when read aloud."""
    text = str(text or "").strip()
    if not text:
        return ""
    text = re.sub(r"```[\s\S]*?```", " Code snippet omitted. ", text)
    text = re.sub(r"`([^`]*)`", r"\1", text)
    text = re.sub(r"!?\[([^\]]+)\]\([^)]+\)", r"\1", text)
    text = re.sub(r"https?://\S+", "link", text)
    text = re.sub(r"^[ \t]{0,3}#{1,6}[ \t]*", "", text, flags=re.MULTILINE)
    text = re.sub(r"^[ \t]*[-*+][ \t]+", "", text, flags=re.MULTILINE)
    text = re.sub(r"^[ \t]*\d+[.)][ \t]+", "", text, flags=re.MULTILINE)
    text = re.sub(r"[*_~]{1,3}", "", text)
    text = re.sub(r"\n\s*\n+", ". ", text)
    text = re.sub(r"\n+", " ", text)
    text = re.sub(r"\s{2,}", " ", text).strip()
    # Avoid unexpectedly long uninterrupted speech. The full answer remains
    # visible in ORI; a short note tells the user where the spoken part ended.
    if len(text) > 2800:
        text = text[:2750].rsplit(" ", 1)[0].rstrip(" ,;:") + ". The rest of the answer is shown on screen."
    return text


def _speak_with_system_voice(text: str, config: dict[str, Any]) -> None:
    """Use installed system voices. On Windows this uses SAPI and works offline."""
    try:
        import pythoncom  # supplied by pywin32 on Windows
    except ImportError:
        pythoncom = None

    com_initialized = False
    engine = None
    try:
        if os.name == "nt" and pythoncom is not None:
            pythoncom.CoInitialize()
            com_initialized = True

        import pyttsx3
        engine = pyttsx3.init("sapi5" if os.name == "nt" else None)
        try:
            rate = int(config.get("tts_rate", 180))
            engine.setProperty("rate", max(120, min(240, rate)))
        except Exception:
            pass

        preferred_voice = str(config.get("sapi_voice", "") or "").strip().lower()
        if preferred_voice:
            try:
                for voice in engine.getProperty("voices"):
                    if preferred_voice in str(getattr(voice, "id", "")).lower() or preferred_voice in str(getattr(voice, "name", "")).lower():
                        engine.setProperty("voice", voice.id)
                        break
            except Exception:
                pass

        engine.say(text)
        engine.runAndWait()
    finally:
        if engine is not None:
            try:
                engine.stop()
            except Exception:
                pass
        if com_initialized and pythoncom is not None:
            try:
                pythoncom.CoUninitialize()
            except Exception:
                pass


def speak_local(text: str, config: dict[str, Any] | None = None) -> str:
    """Speak one answer and return the engine name that succeeded.

    Called from ORI's background response thread, never from the UI thread.
    By default it uses the local system voice. Neural/cloud engines are only
    attempted when the user explicitly chooses one in the config file.
    """
    cfg = dict(config or {})
    prepared = clean_text_for_speech(text)
    if not prepared:
        return "none"

    with _SPEECH_LOCK:
        requested = str(cfg.get("tts_engine", "system") or "system").strip().lower()
        if requested in {"edge", "edgetts", "kokoro", "elevenlabs"}:
            try:
                from core.tts import create_tts_player
                player = create_tts_player(cfg)
                if player.speak(prepared):
                    return requested
            except Exception as exc:
                print(f"[TTS] Optional {requested} engine failed; falling back to system voice: {exc}")

        try:
            _speak_with_system_voice(prepared, cfg)
            return "system voice"
        except Exception as exc:
            if isinstance(exc, ModuleNotFoundError) and exc.name == "pyttsx3":
                raise RuntimeError(
                    "The speech-output package is missing. Close ORI and run setup_ori.bat again."
                ) from exc
            raise RuntimeError(
                "Windows speech output failed. Check that a Windows speech voice is installed and "
                f"your output device is available. Details: {type(exc).__name__}: {exc}"
            ) from exc
