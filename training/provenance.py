"""Immutable base-model and candidate-adapter provenance checks for Titan training."""
from __future__ import annotations

import importlib.metadata
import json
import os
import re
from pathlib import Path
from typing import Any

DEFAULT_BASE_MODEL = "Qwen/Qwen2.5-0.5B-Instruct"
DEFAULT_BASE_MODEL_REVISION = "7ae557604adf67be50417f59c2c2f167def9a775"
COMMIT_SHA_PATTERN = re.compile(r"^[0-9a-f]{40}$")
DIGEST_PATTERN = re.compile(r"^[0-9a-f]{64}$")


def resolve_base_model_revision(base_model: str, requested: str | None = None) -> str:
    """Return an immutable Hub commit SHA; never silently train against a moving branch."""
    revision = (requested if requested is not None else os.environ.get("TITAN_BASE_MODEL_REVISION", "")).strip()
    if not revision and base_model == DEFAULT_BASE_MODEL:
        revision = DEFAULT_BASE_MODEL_REVISION
    if not COMMIT_SHA_PATTERN.fullmatch(revision):
        raise SystemExit(
            "TITAN_BASE_MODEL_REVISION must be a 40-character Hugging Face commit SHA. "
            f"Pin the revision for {base_model}; branch names such as 'main' are not accepted."
        )
    return revision


def installed_versions() -> dict[str, str | None]:
    """Record the runtime versions that produced the candidate adapter."""
    packages = ("torch", "transformers", "datasets", "peft", "trl", "accelerate")
    versions: dict[str, str | None] = {}
    for package in packages:
        try:
            versions[package] = importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError:
            versions[package] = None
    return versions


def verify_training_manifest(
    adapter_path: str | Path,
    base_model: str,
    base_model_revision: str,
    heldout_sha256: str,
) -> dict[str, Any]:
    """Fail closed unless the adapter was trained against this exact base and held-out file."""
    root = Path(adapter_path)
    manifest_path = root / "titan_training_manifest.json"
    if not manifest_path.is_file():
        raise SystemExit("Candidate adapter is missing titan_training_manifest.json; refusing evaluation.")
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SystemExit("Candidate training manifest is unreadable or invalid JSON.") from exc
    if not isinstance(manifest, dict):
        raise SystemExit("Candidate training manifest must be a JSON object.")
    if manifest.get("base_model") != base_model:
        raise SystemExit("Candidate adapter base model does not match the requested evaluation model.")
    if manifest.get("base_model_revision") != base_model_revision:
        raise SystemExit("Candidate adapter was trained from a different base-model revision.")
    if manifest.get("heldout_data_sha256") != heldout_sha256:
        raise SystemExit("Held-out evaluation data changed since training; refusing a mismatched comparison.")
    if manifest.get("method") != "LoRA SFT self-distillation":
        raise SystemExit("Candidate manifest does not identify a supported LoRA SFT run.")
    if not isinstance(manifest.get("rows"), int) or manifest["rows"] < 20:
        raise SystemExit("Candidate manifest does not contain the minimum 20 training examples.")
    if not isinstance(manifest.get("train_data_sha256"), str) or not DIGEST_PATTERN.fullmatch(manifest["train_data_sha256"]):
        raise SystemExit("Candidate manifest is missing a valid training-data SHA-256.")
    if not root.joinpath("adapter_config.json").is_file():
        raise SystemExit("Candidate adapter_config.json is missing.")
    if not any(path.is_file() for path in root.glob("adapter_model.*")):
        raise SystemExit("Candidate adapter weights are missing.")
    return manifest
