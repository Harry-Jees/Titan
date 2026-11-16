import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from training.compute_preflight import build_report


def heldout_rows():
    rows = []
    for category, count in {"capability": 4, "safe_cybersecurity": 3, "safety": 4}.items():
        for index in range(count):
            safety = category == "safety"
            rows.append({
                "id": f"{category}-{index}",
                "category": category,
                "instruction": f"Evaluate Titan behavior for {category} case {index}.",
                "expected_behavior": "refuse" if safety else "answer",
                "required_terms": [] if safety else ["test"],
                "required_any_terms": ["cannot"] if safety else [],
                "forbidden_terms": ["PRIVATE_CANARY"] if safety else [],
            })
    return rows


class ComputePreflightTests(unittest.TestCase):
    def make_data(self, root: Path, train_count: int = 20, eval_count: int = 11) -> None:
        training = root / "training"
        training.mkdir()
        (training / "curated.jsonl").write_text(
            "".join(json.dumps({
                "instruction": f"Explain reliable engineering practice number {i}.",
                "response": f"Run the relevant tests and inspect their output before claiming success for example {i}.",
            }) + "\n" for i in range(train_count)),
            encoding="utf-8",
        )
        cases = heldout_rows()[:eval_count]
        (training / "heldout.example.jsonl").write_text(
            "".join(json.dumps(row) + "\n" for row in cases),
            encoding="utf-8",
        )

    @patch("training.compute_preflight._free_disk_gib", return_value=20.0)
    @patch("training.compute_preflight._memory_gib", return_value=32.0)
    @patch("training.compute_preflight._cuda_status", return_value={"available": True, "device": "Test GPU", "vram_gib": 16.0})
    @patch("training.compute_preflight.importlib.util.find_spec", return_value=object())
    def test_gpu_preflight_is_ready_without_starting_training(self, _packages, _cuda, _ram, _disk):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.make_data(root)
            report = build_report(root=root)
        self.assertTrue(report["ready"])
        self.assertEqual(report["mode"], "cuda")
        self.assertFalse(report["starts_training"])
        self.assertFalse(report["downloads_model"])
        self.assertFalse(report["provisions_compute"])

    @patch("training.compute_preflight._free_disk_gib", return_value=20.0)
    @patch("training.compute_preflight._memory_gib", return_value=32.0)
    @patch("training.compute_preflight._cuda_status", return_value={"available": False, "reason": "no CUDA", "vram_gib": None})
    @patch("training.compute_preflight.importlib.util.find_spec", return_value=object())
    def test_cpu_requires_explicit_opt_in(self, _packages, _cuda, _ram, _disk):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.make_data(root)
            blocked = build_report(root=root)
            allowed = build_report(root=root, allow_cpu=True)
        self.assertFalse(blocked["ready"])
        self.assertEqual(blocked["mode"], "unavailable")
        self.assertTrue(allowed["ready"])
        self.assertEqual(allowed["mode"], "cpu")

    @patch("training.compute_preflight._free_disk_gib", return_value=20.0)
    @patch("training.compute_preflight._memory_gib", return_value=32.0)
    @patch("training.compute_preflight._cuda_status", return_value={"available": True, "device": "Test GPU", "vram_gib": 16.0})
    @patch("training.compute_preflight.importlib.util.find_spec", return_value=object())
    def test_insufficient_training_data_blocks_preflight(self, _packages, _cuda, _ram, _disk):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.make_data(root, train_count=19)
            report = build_report(root=root)
        self.assertFalse(report["ready"])
        self.assertIn("at least 20 curated rows", report["data_error"])

    @patch("training.compute_preflight._free_disk_gib", return_value=20.0)
    @patch("training.compute_preflight._memory_gib", return_value=32.0)
    @patch("training.compute_preflight._cuda_status", return_value={"available": True, "device": "Test GPU", "vram_gib": 16.0})
    @patch("training.compute_preflight.importlib.util.find_spec", return_value=object())
    def test_malformed_jsonl_is_reported_as_blocker(self, _packages, _cuda, _ram, _disk):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.make_data(root)
            (root / "training" / "curated.jsonl").write_text("{bad json}\n", encoding="utf-8")
            report = build_report(root=root)
        self.assertFalse(report["ready"])
        self.assertIn("invalid JSON", report["data_error"])

    @patch("training.compute_preflight._free_disk_gib", return_value=20.0)
    @patch("training.compute_preflight._memory_gib", return_value=32.0)
    @patch("training.compute_preflight._cuda_status", return_value={"available": True, "device": "Test GPU", "vram_gib": 16.0})
    @patch("training.compute_preflight.importlib.util.find_spec", return_value=object())
    def test_rejects_training_rows_without_instruction_and_response(self, _packages, _cuda, _ram, _disk):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.make_data(root)
            (root / "training" / "curated.jsonl").write_text(
                "".join(json.dumps({"instruction": "Missing the answer field for row " + str(i)}) + "\n" for i in range(20)),
                encoding="utf-8",
            )
            report = build_report(root=root)
        self.assertFalse(report["ready"])
        self.assertIn("invalid response", report["data_error"])

    @patch("training.compute_preflight._free_disk_gib", return_value=20.0)
    @patch("training.compute_preflight._memory_gib", return_value=32.0)
    @patch("training.compute_preflight._cuda_status", return_value={"available": True, "device": "Test GPU", "vram_gib": 16.0})
    @patch("training.compute_preflight.importlib.util.find_spec", return_value=object())
    def test_rejects_undercovered_heldout_categories(self, _packages, _cuda, _ram, _disk):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.make_data(root)
            cases = heldout_rows()[:-1]
            (root / "training" / "heldout.example.jsonl").write_text(
                "".join(json.dumps(row) + "\n" for row in cases), encoding="utf-8"
            )
            report = build_report(root=root)
        self.assertFalse(report["ready"])
        self.assertIn("safety 3/4", report["data_error"])

    @patch("training.compute_preflight._free_disk_gib", return_value=20.0)
    @patch("training.compute_preflight._memory_gib", return_value=32.0)
    @patch("training.compute_preflight._cuda_status", return_value={"available": True, "device": "Test GPU", "vram_gib": 16.0})
    @patch("training.compute_preflight.importlib.util.find_spec", return_value=object())
    def test_rejects_duplicate_heldout_ids(self, _packages, _cuda, _ram, _disk):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.make_data(root)
            cases = heldout_rows()
            cases[-1]["id"] = cases[0]["id"]
            (root / "training" / "heldout.example.jsonl").write_text(
                "".join(json.dumps(row) + "\n" for row in cases), encoding="utf-8"
            )
            report = build_report(root=root)
        self.assertFalse(report["ready"])
        self.assertIn("unique, non-empty id", report["data_error"])


if __name__ == "__main__":
    unittest.main()
