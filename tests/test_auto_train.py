import hashlib
import unittest

from training.auto_train import build_dataset, is_public_source


class AutoTrainTests(unittest.TestCase):
    def make_row(self, *, quote="The system stores evidence with provenance."):
        excerpt = ("A source document explains the system. " + quote +
                   " Additional context makes this excerpt useful for understanding the broader research topic. " +
                   "The page includes further details about the system, its design, and the evidence supporting the claim. " +
                   "This additional sentence ensures the stored source excerpt is long enough for grounded training.")
        return {
            "instruction": "According to the cited source, what does Titan store?",
            "response": "Titan stores evidence with provenance. Source evidence: \"" + quote + "\" Source: https://example.org/research",
            "category": "factuality",
            "source_url": "https://example.org/research",
            "supporting_quote": quote,
            "source_excerpt": excerpt,
            "source_excerpt_sha256": hashlib.sha256(excerpt.encode("utf-8")).hexdigest(),
        }

    def test_rejects_private_and_non_https_sources(self):
        self.assertFalse(is_public_source("https://127.0.0.1/private"))
        self.assertFalse(is_public_source("https://localhost/private"))
        self.assertFalse(is_public_source("http://example.org/page"))
        self.assertTrue(is_public_source("https://example.org/page"))

    def test_accepts_only_hash_verified_grounded_public_examples(self):
        rows = build_dataset([self.make_row()])
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["source_type"], "public_source")

    def test_rejects_quote_not_in_answer_or_excerpt(self):
        row = self.make_row()
        row["source_excerpt"] = "This excerpt deliberately omits the supporting evidence."
        row["source_excerpt_sha256"] = hashlib.sha256(row["source_excerpt"].encode("utf-8")).hexdigest()
        self.assertEqual(build_dataset([row]), [])

    def test_rejects_tampered_excerpt_hash(self):
        row = self.make_row()
        row["source_excerpt"] += " tampered"
        self.assertEqual(build_dataset([row]), [])

    def test_deduplicates_normalized_instructions(self):
        first = self.make_row()
        second = self.make_row()
        second["instruction"] = "  ACCORDING TO THE CITED SOURCE, WHAT DOES TITAN STORE? "
        rows = build_dataset([first, second])
        self.assertEqual(len(rows), 1)


if __name__ == "__main__":
    unittest.main()
