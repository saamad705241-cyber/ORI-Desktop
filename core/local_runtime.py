"""Local-first text runtime used by ORI's private preview build.

This runtime talks to Ollama or an OpenAI-compatible local server through
core.llm_client. It intentionally does not import or initialise a cloud model.
The local path accepts typed messages and speaks replies with the operating
system's installed voice. Microphone input, wake word, and desktop-control tools
remain in the separate cloud runtime in main.py for this preview.
"""
from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Any

from core.local_tts import speak_local
from core.llm_client import (
    call_llm_stream,
    check_model_available,
    ensure_ollama_running,
    get_llm_provider,
    get_llm_settings,
)

_SYSTEM_PROMPT = """You are ORI, a helpful personal desktop assistant.
Be accurate, direct, and natural. State uncertainty clearly. Do not claim you
opened apps, changed settings, read files, searched the web, or performed any
other action unless a connected tool actually did it. In this local preview,
you can answer questions and help reason about tasks, but you do not have access
to live web search, microphone input, or desktop-control tools. You can speak
replies aloud through the installed system speech voice. Keep answers concise
unless the user asks for detail."""
_MAX_HISTORY_MESSAGES = 16
_CONFIG_PATH = Path(__file__).resolve().parent.parent / "config" / "api_keys.json"


def _load_runtime_config() -> dict[str, Any]:
    try:
        value = json.loads(_CONFIG_PATH.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except Exception:
        return {}


class LocalAssistantRuntime:
    """Serve typed prompts in the existing ORI UI using a local model."""

    def __init__(self, ui: Any) -> None:
        self.ui = ui
        self._history: list[dict[str, str]] = []
        self._lock = threading.Lock()
        self._busy = False
        self._config = _load_runtime_config()
        # Spoken replies default on in local mode. A user can opt out by adding
        # "tts_enabled": false to config/api_keys.json.
        self._speech_enabled = bool(self._config.get("tts_enabled", True))
        self.ui.on_text_command = self.handle_text

    def start(self) -> None:
        """Announce the active mode without making a model/network call."""
        provider = get_llm_provider()
        _url, model = get_llm_settings()
        self.ui.set_state("LISTENING")
        self.ui.write_log(
            f"SYS: ORI local mode ready ({provider}, {model}; "
            f"spoken replies {'on' if self._speech_enabled else 'off'}). Type a message to start."
        )
        try:
            self.ui.set_local_mode()
        except Exception:
            # UI text/controls are cosmetic; the runtime should still start.
            pass

    def handle_text(self, text: str) -> None:
        text = str(text or "").strip()
        if not text:
            return
        if not self._lock.acquire(blocking=False):
            self.ui.write_log("SYS: ORI is still answering the previous message. Try again shortly.")
            return
        self._busy = True
        threading.Thread(target=self._answer, args=(text,), daemon=True,
                         name="orry-local-chat").start()

    def _answer(self, text: str) -> None:
        try:
            self.ui.set_state("THINKING")
            self._ensure_backend()
            messages = [{"role": "system", "content": _SYSTEM_PROMPT}]
            messages.extend(self._history[-_MAX_HISTORY_MESSAGES:])
            messages.append({"role": "user", "content": text})

            final_text = ""
            streamed_parts: list[str] = []
            for event in call_llm_stream(messages, tools=None, timeout=180):
                kind = event.get("type")
                if kind == "sentence":
                    part = str(event.get("text") or "").strip()
                    if part:
                        streamed_parts.append(part)
                        self.ui.show_content("ORI · LOCAL RESPONSE", " ".join(streamed_parts))
                elif kind == "done":
                    final_text = str(event.get("content") or "").strip()

            if not final_text:
                final_text = " ".join(streamed_parts).strip()
            if not final_text:
                raise RuntimeError("The configured model returned an empty response. Try a different model.")

            self._history.extend([
                {"role": "user", "content": text},
                {"role": "assistant", "content": final_text},
            ])
            self._history = self._history[-_MAX_HISTORY_MESSAGES:]
            self.ui.show_content("ORI · LOCAL RESPONSE", final_text)
            preview = final_text.replace("\n", " ").strip()
            if len(preview) > 600:
                preview = preview[:597] + "..."
            self.ui.write_log(f"ORI: {preview}")

            if self._speech_enabled:
                self.ui.set_state("SPEAKING")
                try:
                    engine_name = speak_local(final_text, self._config)
                    if engine_name != "none":
                        self.ui.write_log(f"SYS: Voice reply played using {engine_name}.")
                except Exception as speech_exc:
                    speech_message = str(speech_exc).strip() or type(speech_exc).__name__
                    self.ui.write_log(f"WRN: Text reply is ready, but voice output failed: {speech_message[:240]}")
                    self.ui.show_content(
                        "ORI · LOCAL RESPONSE · VOICE WARNING",
                        f"{final_text}\n\nVoice output failed: {speech_message}"
                    )
        except Exception as exc:
            message = str(exc).strip() or type(exc).__name__
            self.ui.show_content(
                "LOCAL AI SETUP REQUIRED",
                f"ORI could not get a response from the local model.\n\n{message}\n\n"
                "For Ollama, install Ollama and run: ollama pull llama3.2. "
                "For LM Studio or another compatible server, update config/api_keys.json.",
            )
            self.ui.write_log(f"ERR: Local model request failed: {message[:240]}")
        finally:
            self.ui.set_state("LISTENING")
            self._busy = False
            self._lock.release()

    @staticmethod
    def _ensure_backend() -> None:
        provider = get_llm_provider()
        url, model = get_llm_settings()
        if not ensure_ollama_running(timeout=10):
            if provider == "openai":
                raise RuntimeError(
                    f"Cannot reach the local model server at {url}. Start its local API server, "
                    "then try again."
                )
            raise RuntimeError(
                "Ollama is not reachable. Install Ollama, start it, and run: ollama pull " + model
            )
        if not check_model_available():
            raise RuntimeError(f"Model '{model}' is not installed in Ollama. Run: ollama pull {model}")
