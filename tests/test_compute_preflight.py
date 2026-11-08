import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from training.compute_preflight import build_report


class ComputePreflightTests(unittest.TestCase):
    def make_data(self, root: Path, train_count: int = 20, eval_count: int = 3) -> None:
        training = root / "training"
        training.mkdir()
        (training / "curated.jsonl").write_text(
            "".join(json.dumps({"instruction": f"train {i}"}) + "\n" for i in range(train_count)),
            encoding="utf-8",
        )
        (training / "heldout.example.jsonl").write_text(
            "".join(json.dumps({"instruction": f"eval {i}"}) + "\n" for i in range(eval_count)),
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
        self.assertTrue(any("at least 20 curated rows" in item for item in report["blockers"]))

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
        self.assertEqual(report["data_error"], "Dataset parse failed: JSONDecodeError")


if __name__ == "__main__":
    unittest.main()
