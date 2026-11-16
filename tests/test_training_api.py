import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = (ROOT / "src/index.ts").read_text(encoding="utf-8")

class TrainingApiPrivacyTests(unittest.TestCase):
    def test_training_examples_are_user_scoped(self):
        self.assertIn("FROM training_examples WHERE user_id=?", SOURCE)
        self.assertIn("DELETE FROM training_examples WHERE user_id=?", SOURCE)
        self.assertIn("UPDATE training_examples SET status=?,reviewed_at=CURRENT_TIMESTAMP WHERE user_id=? AND id=?", SOURCE)

    def test_export_contains_only_approved_user_examples(self):
        self.assertIn("FROM training_examples WHERE user_id=? AND status='approved'", SOURCE)
        self.assertIn('source_type: "user_conversation"', SOURCE)
        self.assertIn("consent: true", SOURCE)

    def test_training_preferences_are_explicit_and_user_scoped(self):
        self.assertIn("SELECT enabled,updated_at FROM training_preferences WHERE user_id=?", SOURCE)
        self.assertIn("INSERT INTO training_preferences(user_id,enabled,updated_at)", SOURCE)

if __name__ == "__main__":
    unittest.main()
