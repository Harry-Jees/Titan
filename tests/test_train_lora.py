import unittest
from training.train_lora import validate_training_rows, is_valid_source_url

def row(index: int):
    quote = f"A supporting quote with enough characters {index}"
    return {"instruction":f"Explain reliable test practice number {index}.",
            "response":f"A reliable practice is to run tests and inspect the result for example {index}. {quote}",
            "source_url":f"https://example.org/source/{index}","supporting_quote":quote}

class TrainingDataValidationTests(unittest.TestCase):
    def test_public_source_url_validator_rejects_local_targets(self):
        self.assertTrue(is_valid_source_url("https://docs.python.org/3/"))
        for source in ("http://localhost/","http://service.internal/","http://10.0.0.1/","http://169.254.169.254/","https://example.org:8443/","https://singlelabel/"):
            self.assertFalse(is_valid_source_url(source), source)

    def test_rejects_heldout_overlap_and_duplicate_instructions(self):
        rows=[row(i) for i in range(21)]
        rows.append({**rows[1],"response":rows[1]["response"]+" duplicate"})
        accepted=validate_training_rows(rows,[{"instruction":rows[0]["instruction"]}])
        self.assertEqual(len(accepted),19)
        self.assertNotIn(rows[0]["instruction"],[item["instruction"] for item in accepted])

    def test_rejects_quote_mismatch_and_private_urls(self):
        rows=[row(i) for i in range(20)]
        rows[0]={**rows[0],"supporting_quote":"This quote is not in the answer at all"}
        with self.assertRaises(SystemExit): validate_training_rows(rows,[])
        for source in ("http://localhost/private","http://127.0.0.1/private","https://user:pass@example.org/source"):
            invalid=[row(i) for i in range(20)]
            invalid[0]={**invalid[0],"source_url":source}
            with self.assertRaises(SystemExit): validate_training_rows(invalid,[])

    def test_refuses_secret_shaped_training_content(self):
        rows=[row(i) for i in range(20)]
        rows[0]={**rows[0],"response":"Here is a sk-"+"A"*24+" credential and explanation."}
        with self.assertRaises(SystemExit): validate_training_rows(rows,[])

if __name__ == "__main__": unittest.main()
