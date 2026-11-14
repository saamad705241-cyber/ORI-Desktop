import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class SettingsRemoteRedesignTests(unittest.TestCase):
    def test_settings_builder_uses_category_stack_with_scrollable_content(self):
        source = (ROOT / "ui.py").read_text(encoding="utf-8")
        start = source.index("    def _build_settings_page(self) -> QWidget:")
        end = source.index("    def _select_settings_category(", start)
        section = source[start:end]
        self.assertIn("QStackedWidget", section)
        self.assertIn("QScrollArea", section)
        self.assertIn("setWidgetResizable(True)", section)
        self.assertIn("ScrollBarPolicy.ScrollBarAsNeeded", section)
        self.assertIn("PHONE REMOTE", section)
        self.assertNotIn("01 /", section)
        self.assertNotIn("Firebase", section)
        self.assertNotIn("Browser settings", section)
        self.assertNotIn("Gemini 3.7", section)

    def test_updates_use_one_progressive_action_and_uninstall_is_present(self):
        source = (ROOT / "ui.py").read_text(encoding="utf-8")
        start = source.index("        # ABOUT & UPDATES")
        end = source.index("    def _select_settings_category(", start)
        section = source[start:end]
        self.assertIn('button("CHECK FOR UPDATES", True)', section)
        self.assertIn("self._update_action_btn.clicked.connect(self._handle_update_action)", section)
        self.assertNotIn("_check_updates_btn", section)
        self.assertNotIn("_download_update_btn", section)
        self.assertNotIn("_install_update_btn", section)
        self.assertIn('button("UNINSTALL ORI")', section)
        self.assertIn("Your API key, preferences and ORI memory are kept", section)
        self.assertIn('"download": "DOWNLOAD UPDATE"', source)
        self.assertIn('"install": "OPEN UPDATE ASSISTANT"', source)
        check_method = source.split("    def _apply_app_update_check(", 1)[1].split(
            "    def _download_checked_update(", 1
        )[0]
        self.assertNotIn("_download_app_update(data)", check_method)
        self.assertIn("schedule_windows_update", source)
        self.assertIn("schedule_uninstall", source)

    def test_onboarding_marks_google_and_email_auth_as_coming_soon(self):
        source = (ROOT / "ui.py").read_text(encoding="utf-8")
        self.assertIn("CONTINUE WITH GOOGLE", source)
        self.assertIn("SEND EMAIL CODE", source)
        self.assertIn("Email OTP sign-in is coming soon", source)
        self.assertIn("CONTINUE AS A GUEST", source)

    def test_remote_dashboard_has_dynamic_port_and_authenticated_screenshot_route(self):
        source = (ROOT / "dashboard" / "server.py").read_text(encoding="utf-8")
        self.assertIn("_find_available_port", source)
        self.assertIn("/api/desktop/screenshot", source)
        self.assertIn("if not _auth(req)", source)

    def test_mobile_dashboard_exposes_explicit_pc_screen_action(self):
        source = (ROOT / "dashboard" / "static" / "app.html").read_text(encoding="utf-8")
        self.assertIn("PC SCREEN", source)
        self.assertIn("captureDesktopScreen", source)


if __name__ == "__main__":
    unittest.main()
