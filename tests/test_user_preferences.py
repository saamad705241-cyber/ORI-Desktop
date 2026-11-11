import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from memory import config_manager as cfg


class UserProfilePreferenceTests(unittest.TestCase):
    def test_preference_values_are_normalized(self):
        with tempfile.TemporaryDirectory() as td:
            target = Path(td) / "api_keys.json"
            with patch.object(cfg, "CONFIG_FILE", target), patch.object(cfg, "CONFIG_DIR", Path(td)):
                cfg.save_user_preferences("  Sam  ", "Hinglish", "Concise")
                saved = json.loads(target.read_text(encoding="utf-8"))
                self.assertEqual(saved["user_name"], "Sam")
                self.assertEqual(saved["preferred_language"], "Hinglish")
                self.assertEqual(saved["conversation_style"], "Concise")
                self.assertTrue(saved["guest_mode"])
                self.assertTrue(saved["onboarding_completed"])

    def test_unrecognized_preferences_fall_back_safely(self):
        with tempfile.TemporaryDirectory() as td:
            target = Path(td) / "api_keys.json"
            target.write_text(json.dumps({
                "preferred_language": "Klingon",
                "conversation_style": "angry",
                "metrics_display_mode": "banana",
            }), encoding="utf-8")
            with patch.object(cfg, "CONFIG_FILE", target), patch.object(cfg, "CONFIG_DIR", Path(td)):
                self.assertEqual(cfg.get_preferred_language(), "Auto detect")
                self.assertEqual(cfg.get_conversation_style(), "Natural & friendly")
                self.assertEqual(cfg.get_metrics_display_mode(), "both")

    def test_metrics_mode_is_limited_to_supported_values(self):
        with tempfile.TemporaryDirectory() as td:
            target = Path(td) / "api_keys.json"
            with patch.object(cfg, "CONFIG_FILE", target), patch.object(cfg, "CONFIG_DIR", Path(td)):
                cfg.save_metrics_display_mode("graphs")
                self.assertEqual(cfg.get_metrics_display_mode(), "graphs")
                cfg.save_metrics_display_mode("invalid")
                self.assertEqual(cfg.get_metrics_display_mode(), "both")


if __name__ == "__main__":
    unittest.main()
