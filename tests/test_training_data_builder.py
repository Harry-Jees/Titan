import unittest

from training.build_training_data import validate_candidate


class TrainingDataBuilderTests(unittest.TestCase):
    def setUp(self):
        self.url = "https://docs.example.org/guide"
        self.quote = "Use a prepared statement for every untrusted value."
        self.excerpt = "Database safety guidance: " + self.quote
        self.item = {
            "instruction": "How should database input be handled safely?",
            "response": "Bind untrusted values rather than concatenating SQL. " + self.quote,
            "category": "security",
            "source_url": self.url,
            "supporting_quote": self.quote,
        }

    def test_accepts_quote_grounded_in_source_and_response(self):
        row = validate_candidate(self.item, self.url, self.excerpt)
        self.assertIsNotNone(row)
        self.assertEqual(row["source_type"], "public_source")

    def test_rejects_quote_missing_from_response(self):
        item = {**self.item, "response": "Bind untrusted values rather than concatenating SQL safely."}
        self.assertIsNone(validate_candidate(item, self.url, self.excerpt))

    def test_rejects_quote_missing_from_source_or_wrong_url(self):
        self.assertIsNone(validate_candidate(self.item, self.url, "unrelated source text"))
        self.assertIsNone(validate_candidate(self.item, "https://other.example.org/", self.excerpt))

    def test_rejects_secret_shaped_content(self):
        item = {**self.item, "response": self.item["response"] + " bearer " + "A" * 32}
        self.assertIsNone(validate_candidate(item, self.url, self.excerpt))


if __name__ == "__main__":
    unittest.main()
