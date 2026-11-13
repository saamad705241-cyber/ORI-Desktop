import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class SettingsRemoteRedesignTests(unittest.TestCase):
    def test_settings_builder_uses_category_stack_not_scroll_area(self):
        source = (ROOT / "ui.py").read_text(encoding="utf-8")
        start = source.index("    def _build_settings_page(self) -> QWidget:")
        end = source.index("    def _select_settings_category(", start)
        section = source[start:end]
        self.assertIn("QStackedWidget", section)
        self.assertIn("PHONE REMOTE", section)
        self.assertNotIn("QScrollArea", section)
        self.assertNotIn("01 /", section)
        self.assertNotIn("Firebase", section)
        self.assertNotIn("Browser settings", section)
        self.assertNotIn("Gemini 3.7", section)

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


    def test_about_text_is_scrollable_and_updates_use_one_button(self):
        source = (ROOT / "ui.py").read_text(encoding="utf-8")
        start = source.index("    def _build_settings_page(self) -> QWidget:")
        end = source.index("    def _select_settings_category(", start)
        section = source[start:end]
        self.assertIn("about_text = QTextEdit()", section)
        self.assertIn("about_text.setReadOnly(True)", section)
        self.assertIn('button("CHECK & INSTALL UPDATE", True)', section)
        self.assertNotIn('button("DOWNLOAD UPDATE"', section)
        self.assertNotIn('button("INSTALL & RESTART"', section)
        self.assertNotIn("_check_updates_btn", source)
        self.assertNotIn("_download_update_btn", source)
        self.assertNotIn("_install_update_btn", source)

    def test_voice_system_and_about_settings_use_balanced_columns(self):
        source = (ROOT / "ui.py").read_text(encoding="utf-8")
        start = source.index("    def _build_settings_page(self) -> QWidget:")
        end = source.index("    def _select_settings_category(", start)
        section = source[start:end]
        self.assertIn("voice_columns = QHBoxLayout()", section)
        self.assertIn("system_columns = QHBoxLayout()", section)
        self.assertIn("about_columns = QHBoxLayout()", section)
        self.assertIn("about_text = QTextEdit()", section)
        self.assertIn("about_text.setReadOnly(True)", section)

    def test_update_flow_chains_check_download_and_install(self):
        source = (ROOT / "ui.py").read_text(encoding="utf-8")
        check_handler = source[source.index("    def _apply_app_update_check"):source.index("    def _download_app_update")]
        download_handler = source[source.index("    def _apply_app_update_download"):source.index("    def _install_app_update")]
        self.assertIn("self._download_app_update()", check_handler)
        self.assertIn("self._install_app_update()", download_handler)


if __name__ == "__main__":
    unittest.main()
