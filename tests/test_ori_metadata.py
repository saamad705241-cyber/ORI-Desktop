"""Tests for ori_metadata.py — ORI identity and developer profile."""
import unittest
import ori_metadata as meta


class ORIMetadataTests(unittest.TestCase):

    # ------------------------------------------------------------------
    # ORI acronym / identity
    # ------------------------------------------------------------------

    def test_app_name_is_ori(self):
        self.assertEqual(meta.APP_NAME, "ORI")

    def test_acronym_overcome(self):
        self.assertEqual(meta.ORI_ACRONYM["O"], "Overcome")

    def test_acronym_rebuild(self):
        self.assertEqual(meta.ORI_ACRONYM["R"], "Rebuild")

    def test_acronym_improve(self):
        self.assertEqual(meta.ORI_ACRONYM["I"], "Improve")

    def test_meaning_english_present(self):
        self.assertIn("Overcome", meta.ORI_MEANING_EN)
        self.assertIn("rebuild", meta.ORI_MEANING_EN.lower())
        self.assertIn("improve", meta.ORI_MEANING_EN.lower())

    def test_meaning_hindi_present(self):
        # Hindi meaning must be non-empty
        self.assertTrue(len(meta.ORI_MEANING_HI) > 10)

    def test_tagline_present(self):
        self.assertIn("lesson", meta.ORI_TAGLINE.lower())
        self.assertIn("limit", meta.ORI_TAGLINE.lower())

    def test_never_rename_to_orry(self):
        # Ensure ORRY does not appear as the canonical app name anywhere in metadata
        for attr in ("APP_NAME", "APP_RELEASE_LABEL", "APP_MODEL_LABEL"):
            val = str(getattr(meta, attr, ""))
            self.assertNotEqual(val.upper(), "ORRY", f"{attr} must not be ORRY")

    # ------------------------------------------------------------------
    # Developer profile
    # ------------------------------------------------------------------

    def test_developer_name(self):
        self.assertEqual(meta.DEVELOPER_NAME, "Abdul Samad")

    def test_developer_role_contains_independent(self):
        self.assertIn("independent", meta.DEVELOPER_ROLE.lower())

    def test_developer_role_contains_creator(self):
        self.assertIn("creator", meta.DEVELOPER_ROLE.lower())

    def test_project_start_september_2026(self):
        self.assertIn("September 2026", meta.PROJECT_START_TEXT)

    def test_planned_release_november_2026(self):
        self.assertEqual(meta.PLANNED_FINAL_RELEASE, "November 2026")

    def test_instagram_handle_present(self):
        self.assertIn("_samad02", meta.INSTAGRAM_HANDLE)

    # ------------------------------------------------------------------
    # ABOUT_TEXT completeness
    # ------------------------------------------------------------------

    def test_about_contains_acronym_expansion(self):
        self.assertIn("Overcome", meta.ABOUT_TEXT)
        self.assertIn("Rebuild", meta.ABOUT_TEXT)
        self.assertIn("Improve", meta.ABOUT_TEXT)

    def test_about_contains_tagline(self):
        self.assertIn("lesson", meta.ABOUT_TEXT.lower())
        self.assertIn("limit", meta.ABOUT_TEXT.lower())

    def test_about_contains_planned_release(self):
        self.assertIn("November 2026", meta.ABOUT_TEXT)

    def test_about_does_not_claim_release_shipped(self):
        # The text must clarify that November 2026 is a plan, not a completed release
        self.assertIn("plan", meta.ABOUT_TEXT.lower())

    def test_about_does_not_list_implemented_updater_as_coming_soon(self):
        coming_soon = meta.ABOUT_TEXT.split("Coming soon / not enabled in this build", 1)[-1]
        self.assertNotIn("GitHub release checks", coming_soon)
        self.assertIn("SHA-256", meta.ABOUT_TEXT)
        self.assertIn("startup" , meta.ABOUT_TEXT.lower())

    # ------------------------------------------------------------------
    # ASSISTANT_KNOWLEDGE_TEXT completeness
    # ------------------------------------------------------------------

    def test_knowledge_contains_ori_acronym(self):
        self.assertIn("O — Overcome", meta.ASSISTANT_KNOWLEDGE_TEXT)

    def test_knowledge_contains_tagline(self):
        self.assertIn("lesson", meta.ASSISTANT_KNOWLEDGE_TEXT.lower())

    def test_knowledge_contains_developer_name(self):
        self.assertIn("Abdul Samad", meta.ASSISTANT_KNOWLEDGE_TEXT)

    def test_knowledge_anti_impersonation_rule(self):
        # The knowledge text must tell the AI not to grant privileges from a chat name claim
        text = meta.ASSISTANT_KNOWLEDGE_TEXT.lower()
        self.assertTrue(
            "does not authenticate" in text
            or "does not grant" in text
            or "cannot authenticate" in text
            or "normal conversation" in text,
            "Anti-impersonation rule missing from ASSISTANT_KNOWLEDGE_TEXT",
        )

    # ------------------------------------------------------------------
    # RESTRICTIONS_TEXT
    # ------------------------------------------------------------------

    def test_restrictions_no_credential_exposure(self):
        text = meta.RESTRICTIONS_TEXT.lower()
        self.assertIn("api key", text)
        # Must say never reveal / repeat
        self.assertTrue(
            "never" in text or "do not" in text,
            "Credential protection rule missing from RESTRICTIONS_TEXT",
        )

    def test_restrictions_orry_guard(self):
        self.assertIn("ORRY", meta.RESTRICTIONS_TEXT)

    # ------------------------------------------------------------------
    # TERMS_TEXT
    # ------------------------------------------------------------------

    def test_terms_contains_developer(self):
        self.assertIn("Abdul Samad", meta.TERMS_TEXT)

    def test_terms_contains_ai_disclaimer(self):
        text = meta.TERMS_TEXT.lower()
        self.assertIn("inaccurate", text)


if __name__ == "__main__":
    unittest.main()
