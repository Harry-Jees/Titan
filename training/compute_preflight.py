"""Read-only compute and dataset preflight for Titan LoRA training.

This module never downloads models, starts training, contacts a teacher API, or
provisions remote compute. It validates the dataset contract before reporting readiness.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import shutil
import sys
from collections import Counter
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
REQUIRED_PACKAGES = ("torch", "transformers", "datasets", "peft", "trl")
MIN_GPU_VRAM_GIB = 8
MIN_CPU_RAM_GIB = 16
MIN_FREE_DISK_GIB = 10
MIN_TRAINING_ROWS = 20
MIN_HELDOUT_COUNTS = {"capability": 4, "safe_cybersecurity": 3, "safety": 4}
ALLOWED_CATEGORIES = set(MIN_HELDOUT_COUNTS) | {
    "coding", "factuality", "reasoning", "tool_use", "privacy", "instruction_following"
}


def _memory_gib() -> float | None:
    try:
        pages = os.sysconf("SC_PHYS_PAGES")
        page_size = os.sysconf("SC_PAGE_SIZE")
        return pages * page_size / (1024 ** 3)
    except (AttributeError, OSError, ValueError):
        return None


def _free_disk_gib(path: Path) -> float | None:
    try:
        return shutil.disk_usage(path).free / (1024 ** 3)
    except OSError:
        return None


def _cuda_status() -> dict[str, Any]:
    if importlib.util.find_spec("torch") is None:
        return {"available": False, "reason": "PyTorch is not installed", "vram_gib": None}
    try:
        import torch  # type: ignore

        if not torch.cuda.is_available():
            return {"available": False, "reason": "PyTorch cannot access CUDA", "vram_gib": None}
        properties = torch.cuda.get_device_properties(0)
        return {
            "available": True,
            "device": properties.name,
            "vram_gib": round(properties.total_memory / (1024 ** 3), 2),
        }
    except Exception as exc:
        return {"available": False, "reason": f"CUDA probe failed: {type(exc).__name__}", "vram_gib": None}


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        raise ValueError(f"Dataset file missing: {path}")
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as stream:
        for line_no, line in enumerate(stream, 1):
            if not line.strip():
                continue
            try:
                item = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"invalid JSON at line {line_no}") from exc
            if not isinstance(item, dict):
                raise ValueError(f"line {line_no} must contain a JSON object")
            rows.append(item)
    return rows


def _validate_training_data(path: Path) -> int:
    rows = _load_jsonl(path)
    if len(rows) < MIN_TRAINING_ROWS:
        raise ValueError(f"need at least {MIN_TRAINING_ROWS} curated rows (found {len(rows)})")
    for index, row in enumerate(rows, 1):
        instruction = row.get("instruction")
        response = row.get("response")
        if not isinstance(instruction, str) or len(instruction.strip()) < 12:
            raise ValueError(f"training row {index} has an invalid instruction")
        if not isinstance(response, str) or not 30 <= len(response.strip()) <= 6000:
            raise ValueError(f"training row {index} has an invalid response")
    return len(rows)


def _validate_heldout_data(path: Path) -> int:
    rows = _load_jsonl(path)
    if not rows:
        raise ValueError("held-out dataset is empty")
    ids: set[str] = set()
    counts: Counter[str] = Counter()
    for index, row in enumerate(rows, 1):
        case_id = row.get("id")
        instruction = row.get("instruction")
        category = row.get("category")
        expected = row.get("expected_behavior")
        if not isinstance(case_id, str) or not case_id.strip() or case_id in ids:
            raise ValueError(f"held-out row {index} requires a unique, non-empty id")
        ids.add(case_id)
        if not isinstance(instruction, str) or not instruction.strip():
            raise ValueError(f"held-out row {index} requires a non-empty instruction")
        if category not in ALLOWED_CATEGORIES:
            raise ValueError(f"held-out row {index} has an unsupported category")
        if expected not in {"answer", "refuse"}:
            raise ValueError(f"held-out row {index} has an invalid expected_behavior")
        for field in ("required_terms", "required_any_terms", "forbidden_terms"):
            terms = row.get(field, [])
            if not isinstance(terms, list) or any(not isinstance(term, str) or not term.strip() for term in terms):
                raise ValueError(f"held-out row {index} has invalid {field}")
        if category == "safety":
            if expected != "refuse" or not row.get("required_any_terms") or not row.get("forbidden_terms"):
                raise ValueError(f"safety row {index} needs refusal markers and forbidden canaries")
        elif expected != "answer" or not (row.get("required_terms") or row.get("required_any_terms")):
            raise ValueError(f"capability row {index} needs answer scoring terms")
        counts[category] += 1
    missing = [f"{name} {counts[name]}/{minimum}" for name, minimum in MIN_HELDOUT_COUNTS.items() if counts[name] < minimum]
    if missing:
        raise ValueError("held-out category coverage is insufficient: " + ", ".join(missing))
    return len(rows)


def build_report(*, allow_cpu: bool = False, root: Path = ROOT) -> dict[str, Any]:
    packages = {name: importlib.util.find_spec(name) is not None for name in REQUIRED_PACKAGES}
    cuda = _cuda_status()
    ram_gib = _memory_gib()
    free_disk_gib = _free_disk_gib(root)

    train_path = Path(os.environ.get("TITAN_TRAIN_DATA", "training/curated.jsonl"))
    eval_path = Path(os.environ.get("TITAN_EVAL_DATA", "training/heldout.example.jsonl"))
    if not train_path.is_absolute():
        train_path = root / train_path
    if not eval_path.is_absolute():
        eval_path = root / eval_path

    try:
        train_rows = _validate_training_data(train_path)
        eval_rows = _validate_heldout_data(eval_path)
        data_error = None
    except (OSError, ValueError) as exc:
        train_rows, eval_rows = -1, -1
        data_error = f"Dataset validation failed: {exc}"

    missing_packages = [name for name, present in packages.items() if not present]
    gpu_ready = bool(cuda.get("available") and (cuda.get("vram_gib") or 0) >= MIN_GPU_VRAM_GIB)
    cpu_ready = bool(allow_cpu and ram_gib is not None and ram_gib >= MIN_CPU_RAM_GIB)
    data_ready = train_rows >= MIN_TRAINING_ROWS and eval_rows > 0 and data_error is None
    disk_ready = free_disk_gib is not None and free_disk_gib >= MIN_FREE_DISK_GIB

    blockers = []
    if missing_packages:
        blockers.append("Missing training packages: " + ", ".join(missing_packages))
    if not gpu_ready and not cpu_ready:
        if allow_cpu:
            blockers.append(f"CPU fallback requires at least {MIN_CPU_RAM_GIB} GiB RAM")
        else:
            blockers.append("CUDA GPU with at least 8 GiB VRAM unavailable; pass --allow-cpu only on a machine with at least 16 GiB RAM")
    if not data_ready:
        blockers.append(data_error or "Training or held-out dataset validation failed")
    if not disk_ready:
        blockers.append(f"At least {MIN_FREE_DISK_GIB} GiB free disk space is required")

    return {
        "ready": not blockers,
        "mode": "cuda" if gpu_ready else ("cpu" if cpu_ready else "unavailable"),
        "cuda": cuda,
        "ram_gib": round(ram_gib, 2) if ram_gib is not None else None,
        "free_disk_gib": round(free_disk_gib, 2) if free_disk_gib is not None else None,
        "packages": packages,
        "training_rows": train_rows,
        "heldout_rows": eval_rows,
        "data_error": data_error,
        "model_revision": "7ae557604adf67be50417f59c2c2f167def9a775",
        "starts_training": False,
        "downloads_model": False,
        "provisions_compute": False,
        "blockers": blockers,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--allow-cpu", action="store_true", help="Allow CPU-only training if RAM is at least 16 GiB")
    args = parser.parse_args()
    report = build_report(allow_cpu=args.allow_cpu)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["ready"] else 2


if __name__ == "__main__":
    sys.exit(main())
