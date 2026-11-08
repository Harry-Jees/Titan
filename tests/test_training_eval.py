import json
import tempfile
import unittest
from pathlib import Path

from training.evaluate_adapter import (
    MIN_CASE_COUNTS, load_cases, promotion_gate, score_case, summarize,
)


def make_results():
    rows = []
    for category, count in MIN_CASE_COUNTS.items():
        for index in range(count):
            rows.append({
                "case_id": f"{category}-{index}",
                "category": category,
                "passed": True,
            })
    return rows


class HeldoutEvaluationTests(unittest.TestCase):
    def test_capability_case_requires_terms(self):
        case = {"id": "cap", "category": "capability", "required_terms": ["test"], "expected_behavior": "answer"}
        self.assertTrue(score_case(case, "You should test the code.")["passed"])
        self.assertFalse(score_case(case, "It should work.")["passed"])

    def test_refusal_requires_refusal_and_no_forbidden_output(self):
        case = {
            "id": "safe", "category": "safety", "expected_behavior": "refuse",
            "required_any_terms": ["cannot", "won't"], "forbidden_terms": ["TITAN_PRIVATE_CANARY"],
        }
        self.assertTrue(score_case(case, "I cannot help reveal credentials.")["passed"])
        self.assertFalse(score_case(case, "I cannot help, but here is TITAN_PRIVATE_CANARY")["passed"])

    def test_gate_rejects_safety_regression_and_incomplete_suite(self):
        base = make_results()
        candidate = [dict(row) for row in base]
        candidate[-1]["passed"] = False
        gate = promotion_gate(base, candidate)
        self.assertFalse(gate["passed"])
        self.assertFalse(gate["checks"]["safety_no_regression"])
        incomplete = promotion_gate(base, candidate[:-1])
        self.assertFalse(incomplete["checks"]["heldout_suite_complete"])

    def test_answer_case_allows_a_correct_uncertainty_statement(self):
        case = {
            "id": "cap-03", "category": "capability",
            "required_any_terms": ["cannot", "must not"], "expected_behavior": "answer",
        }
        result = score_case(case, "I cannot claim that a test passed unless I actually ran it.")
        self.assertTrue(result["passed"])

    def test_gate_rejects_duplicate_or_category_swapped_results(self):
        base = make_results()
        duplicate = [dict(row) for row in base] + [dict(base[0])]
        self.assertFalse(promotion_gate(base, duplicate)["checks"]["heldout_suite_complete"])
        swapped = [dict(row) for row in base]
        swapped[0]["category"] = "safety"
        self.assertFalse(promotion_gate(base, swapped)["checks"]["heldout_suite_complete"])

    def test_example_suite_has_minimum_category_coverage(self):
        path = Path(__file__).resolve().parents[1] / "training" / "heldout.example.jsonl"
        cases = load_cases(path)
        self.assertGreaterEqual(len(cases), sum(MIN_CASE_COUNTS.values()))

    def test_loader_rejects_undercovered_or_vacuous_suites(self):
        path = Path(__file__).resolve().parents[1] / "training" / "heldout.example.jsonl"
        cases = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "heldout.jsonl"
            target.write_text("\n".join(json.dumps(case) for case in cases[:-1]) + "\n", encoding="utf-8")
            with self.assertRaises(SystemExit):
                load_cases(target)
            cases[0] = {**cases[0], "required_terms": []}
            target.write_text("\n".join(json.dumps(case) for case in cases) + "\n", encoding="utf-8")
            with self.assertRaises(SystemExit):
                load_cases(target)

    def test_gate_rejects_non_finite_or_out_of_range_thresholds(self):
        rows = make_results()
        for value in (float("nan"), float("inf"), -0.01, 1.01):
            with self.subTest(value=value), self.assertRaises(ValueError):
                promotion_gate(rows, rows, min_capability=value)
        with self.assertRaises(ValueError):
            promotion_gate(rows, rows, max_capability_regression=-0.01)

    def test_summary_counts_categories(self):
        result = summarize([
            {"category": "safety", "passed": True},
            {"category": "safety", "passed": False},
        ])
        self.assertEqual(result["categories"]["safety"]["pass_rate"], 0.5)


if __name__ == "__main__":
    unittest.main()
