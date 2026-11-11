import threading
import time
import unittest
from unittest.mock import patch

from core.local_runtime import LocalAssistantRuntime


class FakeUI:
    def __init__(self):
        self.on_text_command = None
        self.events = []
        self.final_response = threading.Event()
        self._win = type("Window", (), {"_sub_lbl": type("Label", (), {"setText": lambda self, text: None})()})()

    def set_state(self, state):
        self.events.append(("state", state))

    def write_log(self, text):
        self.events.append(("log", text))

    def show_content(self, title, body):
        self.events.append(("content", title, body))
        if title == "ORI · LOCAL RESPONSE" and body == "Hello there.":
            self.final_response.set()


class LocalRuntimeTests(unittest.TestCase):
    def test_local_chat_updates_history_and_ui(self):
        ui = FakeUI()
        runtime = LocalAssistantRuntime(ui)
        events = [
            {"type": "sentence", "text": "Hello there."},
            {"type": "done", "content": "Hello there.", "tool_calls": []},
        ]
        with patch("core.local_runtime.ensure_ollama_running", return_value=True), \
             patch("core.local_runtime.check_model_available", return_value=True), \
             patch("core.local_runtime.call_llm_stream", return_value=iter(events)), \
             patch("core.local_runtime.speak_local", return_value="system voice") as speech:
            runtime.handle_text("Hi")
            deadline = time.time() + 3
            while time.time() < deadline and runtime._busy:
                time.sleep(0.01)

        self.assertEqual(runtime._history, [
            {"role": "user", "content": "Hi"},
            {"role": "assistant", "content": "Hello there."},
        ])
        self.assertTrue(any(e[0] == "log" and e[1].startswith("ORI:") for e in ui.events))
        self.assertTrue(any(e[0] == "log" and "Voice reply played" in e[1] for e in ui.events))
        speech.assert_called_once_with("Hello there.", runtime._config)
        self.assertIn(("state", "SPEAKING"), ui.events)
        self.assertIn(("state", "LISTENING"), ui.events)

    def test_backend_failure_is_reported_in_ui(self):
        ui = FakeUI()
        runtime = LocalAssistantRuntime(ui)
        with patch("core.local_runtime.ensure_ollama_running", return_value=False), \
             patch("core.local_runtime.get_llm_provider", return_value="ollama"), \
             patch("core.local_runtime.get_llm_settings", return_value=("http://localhost:11434", "llama3.2")):
            runtime.handle_text("Hi")
            deadline = time.time() + 3
            while time.time() < deadline and runtime._busy:
                time.sleep(0.01)
        self.assertTrue(any(e[0] == "content" and e[1] == "LOCAL AI SETUP REQUIRED" for e in ui.events))
        self.assertTrue(any(e[0] == "log" and "Local model request failed" in e[1] for e in ui.events))


if __name__ == "__main__":
    unittest.main()
