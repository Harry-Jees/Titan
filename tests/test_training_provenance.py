import json
import tempfile
import unittest
from pathlib import Path

from training.provenance import (
    DEFAULT_BASE_MODEL,
    DEFAULT_BASE_MODEL_REVISION,
    resolve_base_model_revision,
    verify_training_manifest,
)


class TrainingProvenanceTests(unittest.TestCase):
    def test_default_model_uses_an_immutable_pinned_revision(self):
        self.assertEqual(resolve_base_model_revision(DEFAULT_BASE_MODEL), DEFAULT_BASE_MODEL_REVISION)
        self.assertEqual(len(DEFAULT_BASE_MODEL_REVISION), 40)

    def test_custom_model_requires_a_full_commit_sha(self):
        revision = "a" * 40
        self.assertEqual(resolve_base_model_revision("org/custom-model", revision), revision)
        for value in ("", "main", "v1.0", "a" * 39, "g" * 40):
            with self.subTest(value=value), self.assertRaises(SystemExit):
                resolve_base_model_revision("org/custom-model", value)

    def test_manifest_binds_adapter_to_base_revision_and_heldout_digest(self):
        heldout_sha = "b" * 64
        manifest = {
            "base_model": DEFAULT_BASE_MODEL,
            "base_model_revision": DEFAULT_BASE_MODEL_REVISION,
            "heldout_data_sha256": heldout_sha,
            "train_data_sha256": "c" * 64,
            "rows": 20,
            "method": "LoRA SFT self-distillation",
        }
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "adapter_config.json").write_text("{}", encoding="utf-8")
            (root / "adapter_model.safetensors").write_bytes(b"test-adapter")
            (root / "titan_training_manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
            result = verify_training_manifest(root, DEFAULT_BASE_MODEL, DEFAULT_BASE_MODEL_REVISION, heldout_sha)
            self.assertEqual(result["train_data_sha256"], "c" * 64)
            with self.assertRaises(SystemExit):
                verify_training_manifest(root, DEFAULT_BASE_MODEL, "d" * 40, heldout_sha)
            with self.assertRaises(SystemExit):
                verify_training_manifest(root, DEFAULT_BASE_MODEL, DEFAULT_BASE_MODEL_REVISION, "e" * 64)

    def test_manifest_requires_adapter_weights(self):
        manifest = {
            "base_model": DEFAULT_BASE_MODEL,
            "base_model_revision": DEFAULT_BASE_MODEL_REVISION,
            "heldout_data_sha256": "b" * 64,
            "train_data_sha256": "c" * 64,
            "rows": 20,
            "method": "LoRA SFT self-distillation",
        }
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "adapter_config.json").write_text("{}", encoding="utf-8")
            (root / "titan_training_manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
            with self.assertRaises(SystemExit):
                verify_training_manifest(root, DEFAULT_BASE_MODEL, DEFAULT_BASE_MODEL_REVISION, "b" * 64)


if __name__ == "__main__":
    unittest.main()
