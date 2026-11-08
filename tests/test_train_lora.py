import hashlib
import unittest
import training.train_lora as train_lora
from training.train_lora import validate_training_rows, is_valid_source_url

def row(index: int):
    quote = f"A supporting quote with enough characters {index}"
    excerpt = ("A public source explains careful engineering practices. " * 3) + quote + (" More source context is included. " * 3)
    return {
        "instruction": f"Explain reliable test practice number {index}.",
        "response": f"A reliable practice is to run tests and inspect the result for example {index}. {quote}",
        "source_url": f"https://docs.example.org/source/{index}",
        "supporting_quote": quote,
        "source_excerpt": excerpt,
        "source_excerpt_sha256": hashlib.sha256(excerpt.encode("utf-8")).hexdigest(),
        "source_type": "public_source",
    }

class TrainingDataValidationTests(unittest.TestCase):
    def test_public_source_url_validator_rejects_local_targets(self):
        self.assertTrue(is_valid_source_url("https://docs.python.org/3/"))
        for source in ("http://localhost/", "http://service.internal/", "http://10.0.0.1/", "http://169.254.169.254/", "https://example.org:8443/", "https://singlelabel/"):
            self.assertFalse(is_valid_source_url(source), source)

    def test_rejects_heldout_overlap_and_duplicate_instructions(self):
        rows = [row(i) for i in range(21)]
        rows.append({**rows[1], "response": rows[1]["response"] + " duplicate"})
        accepted = validate_training_rows(rows, [{"instruction": rows[0]["instruction"]}])
        self.assertEqual(len(accepted), 20)
        self.assertNotIn(rows[0]["instruction"], [item["instruction"] for item in accepted])

    def test_rejects_quote_mismatch_and_private_urls(self):
        rows = [row(i) for i in range(20)]
        rows[0] = {**rows[0], "supporting_quote": "This quote is not in the answer at all"}
        with self.assertRaises(SystemExit):
            validate_training_rows(rows, [])
        for source in ("http://localhost/private", "http://127.0.0.1/private", "https://user:pass@example.org/source"):
            invalid = [row(i) for i in range(20)]
            invalid[0] = {**invalid[0], "source_url": source}
            with self.assertRaises(SystemExit):
                validate_training_rows(invalid, [])

    def test_quote_must_exist_in_the_saved_source_excerpt(self):
        rows = [row(i) for i in range(20)]
        rows[0]["source_excerpt"] = "This excerpt does not contain the cited supporting quote. " * 5
        rows[0]["source_excerpt_sha256"] = hashlib.sha256(rows[0]["source_excerpt"].encode("utf-8")).hexdigest()
        with self.assertRaises(SystemExit):
            validate_training_rows(rows, [])

    def test_source_excerpt_digest_must_match(self):
        rows = [row(i) for i in range(20)]
        rows[0]["source_excerpt_sha256"] = "0" * 64
        with self.assertRaises(SystemExit):
            validate_training_rows(rows, [])

    def test_user_conversation_data_requires_explicit_export_consent(self):
        rows = []
        for i in range(20):
            rows.append({
                "instruction": f"Explain a user-approved concept number {i}.",
                "response": f"This is a user-approved answer with sufficient detail for training example number {i}.",
                "source_type": "user_conversation",
                "consent": True,
            })
        with self.assertRaises(SystemExit):
            validate_training_rows(rows, [])
        train_lora.ALLOW_USER_CONVERSATION_DATA = True
        try:
            accepted = validate_training_rows(rows, [])
            self.assertEqual(len(accepted), 20)
        finally:
            train_lora.ALLOW_USER_CONVERSATION_DATA = False

    def test_refuses_secret_shaped_training_content(self):
        rows = [row(i) for i in range(20)]
        rows[0] = {**rows[0], "response": "Here is a sk-" + "A" * 24 + " credential and explanation."}
        with self.assertRaises(SystemExit):
            validate_training_rows(rows, [])

if __name__ == "__main__":
    unittest.main()
