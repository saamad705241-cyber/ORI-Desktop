import sys
import types
import unittest
from unittest.mock import Mock, patch

from core.local_tts import clean_text_for_speech, speak_local


class LocalTTSTests(unittest.TestCase):
    def test_clean_text_removes_markdown_for_speech(self):
        self.assertEqual(
            clean_text_for_speech("## Hello **Samad**\n\n- Welcome to `ORI`!"),
            "Hello Samad. Welcome to ORI!",
        )

    def test_default_uses_offline_system_voice(self):
        with patch("core.local_tts._speak_with_system_voice") as system_voice:
            engine = speak_local("Hello ORI", {"tts_engine": "system"})
        self.assertEqual(engine, "system voice")
        system_voice.assert_called_once()

    def test_optional_tts_falls_back_to_system_voice(self):
        fake_tts = types.ModuleType("core.tts")
        fake_tts.create_tts_player = Mock(side_effect=ImportError("optional TTS not installed"))
        with (patch.dict(sys.modules, {"core.tts": fake_tts}),
              patch("core.local_tts._speak_with_system_voice") as system_voice):
            engine = speak_local("Hello ORI", {"tts_engine": "edgetts"})
        self.assertEqual(engine, "system voice")
        system_voice.assert_called_once()


if __name__ == "__main__":
    unittest.main()
