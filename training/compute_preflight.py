"""Read-only compute and dataset preflight for Titan LoRA training.

This module never downloads models, starts training, contacts a teacher API, or
provisions remote compute. It reports whether the current machine is ready.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
REQUIRED_PACKAGES = ("torch", "transformers", "datasets", "peft", "trl")
MIN_GPU_VRAM_GIB = 8
MIN_CPU_RAM_GIB = 16
MIN_FREE_DISK_GIB = 10
MIN_TRAINING_ROWS = 20


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
    except Exception as exc:  # report hardware discovery failures without hiding them
        return {"available": False, "reason": f"CUDA probe failed: {type(exc).__name__}", "vram_gib": None}


def _jsonl_count(path: Path) -> int:
    if not path.is_file():
        return -1
    count = 0
    with path.open("r", encoding="utf-8") as stream:
        for line in stream:
            if line.strip():
                json.loads(line)
                count += 1
    return count


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
        train_rows = _jsonl_count(train_path)
        eval_rows = _jsonl_count(eval_path)
        data_error = None
    except (OSError, json.JSONDecodeError) as exc:
        train_rows, eval_rows = -1, -1
        data_error = f"Dataset parse failed: {type(exc).__name__}"

    missing_packages = [name for name, present in packages.items() if not present]
    gpu_ready = bool(cuda.get("available") and (cuda.get("vram_gib") or 0) >= MIN_GPU_VRAM_GIB)
    cpu_ready = bool(allow_cpu and ram_gib is not None and ram_gib >= MIN_CPU_RAM_GIB)
    hardware_ready = gpu_ready or cpu_ready
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
        blockers.append(data_error or f"Need at least {MIN_TRAINING_ROWS} curated rows and a non-empty held-out dataset (found {train_rows} and {eval_rows})")
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
