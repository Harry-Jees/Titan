#!/usr/bin/env python3
"""Local, cost-capped RAG-to-LoRA runner.

Polls Titan's authenticated evidence-only RAG export. It trains only on this
machine, only when the corpus threshold and local CUDA preflight both pass.
It never provisions cloud compute, calls a teacher API, or deploys an adapter.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "training" / "auto_curated.jsonl"
STATE = ROOT / "training" / "auto_train_state.json"
MIN_EXAMPLES = max(20, int(os.environ.get("TITAN_AUTO_MIN_EXAMPLES", "100")))
MIN_NEW_EXAMPLES = max(1, int(os.environ.get("TITAN_AUTO_MIN_NEW_EXAMPLES", "20")))
MIN_SOURCE_DOMAINS = max(1, int(os.environ.get("TITAN_AUTO_MIN_DOMAINS", "10")))
POLL_SECONDS = max(900, int(os.environ.get("TITAN_AUTO_POLL_SECONDS", "21600")))


def request_export() -> list[dict]:
    endpoint = os.environ.get("TITAN_TRAINING_EXPORT_URL", "").strip()
    token = os.environ.get("TITAN_ADMIN_TOKEN", "")
    if not endpoint or not token:
        raise RuntimeError("Set TITAN_TRAINING_EXPORT_URL and TITAN_ADMIN_TOKEN.")
    parsed = urlparse(endpoint)
    if parsed.scheme != "https" or not parsed.hostname:
        raise RuntimeError("Training export endpoint must be an HTTPS URL.")
    req = urllib.request.Request(
        endpoint,
        data=b"{}",
        headers={"Authorization": "Bearer " + token, "Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=45) as response:
        payload = json.loads(response.read())
    rows = payload.get("rows")
    if not isinstance(rows, list):
        raise RuntimeError("Titan training export returned no rows array.")
    return rows


def normalize(value: str) -> str:
    return " ".join(value.split()).casefold()


def build_dataset(exported: list[dict]) -> list[dict]:
    accepted: list[dict] = []
    seen: set[str] = set()
    for row in exported:
        if not isinstance(row, dict):
            continue
        source = str(row.get("source_url", "")).strip()
        quote = str(row.get("supporting_quote", "")).strip()
        excerpt = str(row.get("source_excerpt", "")).strip()[:6500]
        subject = str(row.get("instruction", "")).strip()
        response = str(row.get("response", "")).strip()
        digest = str(row.get("source_excerpt_sha256", "")).strip().lower()
        if not source.startswith("https://") or not quote or len(subject) < 12 or len(response) < 30:
            continue
        if normalize(quote) not in normalize(excerpt) or normalize(quote) not in normalize(response):
            continue
        if hashlib.sha256(excerpt.encode("utf-8")).hexdigest() != digest:
            continue
        key = normalize(subject)
        if key in seen:
            continue
        seen.add(key)
        accepted.append({
            "instruction": subject,
            "response": response,
            "category": str(row.get("category", "factuality")),
            "source_url": source,
            "supporting_quote": quote,
            "source_excerpt": excerpt,
            "source_excerpt_sha256": digest,
            "source_type": "public_source",
        })
    accepted.sort(key=lambda item: normalize(item["instruction"]))
    return accepted


def read_state() -> dict:
    try:
        value = json.loads(STATE.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except (OSError, ValueError):
        return {}


def write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8")
    temporary.replace(path)


def run_command(command: list[str], env: dict[str, str]) -> None:
    subprocess.run(command, cwd=ROOT, env=env, check=True)


def cycle() -> dict:
    rows = build_dataset(request_export())
    domains = {urlparse(row["source_url"]).hostname for row in rows}
    digest = hashlib.sha256("".join(
        json.dumps(row, sort_keys=True, ensure_ascii=False) + "\n" for row in rows
    ).encode("utf-8")).hexdigest()
    previous = read_state()
    previous_digest = str(previous.get("successful_dataset_sha256", ""))
    previous_fingerprints = set(previous.get("successful_prompt_fingerprints", []))
    fingerprints = {hashlib.sha256(json.dumps(row, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest() for row in rows}
    new_examples = len(fingerprints - previous_fingerprints)

    report = {
        "examples": len(rows),
        "source_domains": len(domains),
        "new_examples_since_success": new_examples,
        "dataset_sha256": digest,
        "training_started": False,
        "reason": "",
    }
    if len(rows) < MIN_EXAMPLES or len(domains) < MIN_SOURCE_DOMAINS:
        report["reason"] = "RAG corpus has not reached the minimum example/domain threshold."
        return report
    if digest == previous_digest or new_examples < MIN_NEW_EXAMPLES:
        report["reason"] = "Not enough new evidence since the previous successful training cycle."
        return report
    if digest == previous.get("last_failed_dataset_sha256"):
        report["reason"] = "This exact dataset failed training previously; waiting for new evidence before retrying."
        return report

    write_jsonl(DATA, rows)
    env = os.environ.copy()
    env["TITAN_TRAIN_DATA"] = str(DATA)
    env["TITAN_EVAL_DATA"] = env.get("TITAN_EVAL_DATA", "training/heldout.example.jsonl")
    env["TITAN_BASE_MODEL"] = env.get("TITAN_BASE_MODEL", "Qwen/Qwen2.5-0.5B-Instruct")
    adapter = ROOT / "artifacts" / ("titan-rag-lora-" + digest[:12])
    env["TITAN_ADAPTER_OUT"] = str(adapter)
    env["TITAN_ADAPTER_PATH"] = str(adapter)

    # Preflight is read-only. No CPU fallback and no remote GPU provisioning.
    run_command([sys.executable, "training/compute_preflight.py"], env)
    report["training_started"] = True
    try:
        run_command([sys.executable, "training/train_lora.py"], env)
        run_command([sys.executable, "training/evaluate_adapter.py"], env)
    except subprocess.CalledProcessError:
        previous["last_failed_dataset_sha256"] = digest
        previous["last_failed_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        STATE.write_text(json.dumps(previous, indent=2), encoding="utf-8")
        raise

    previous.update({
        "successful_dataset_sha256": digest,
        "successful_examples": len(rows),
        "successful_prompt_fingerprints": sorted(fingerprints),
        "last_successful_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "candidate_adapter": str(adapter.relative_to(ROOT)),
        "promotion": "not promoted; candidate requires human review",
    })
    STATE.parent.mkdir(parents=True, exist_ok=True)
    STATE.write_text(json.dumps(previous, indent=2), encoding="utf-8")
    report["candidate_adapter"] = str(adapter.relative_to(ROOT))
    report["reason"] = "Candidate trained and passed the configured held-out gate; not deployed."
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--watch", action="store_true", help="Poll the RAG export every six hours (configurable).")
    args = parser.parse_args()
    while True:
        try:
            print(json.dumps(cycle(), indent=2), flush=True)
        except urllib.error.HTTPError as exc:
            print(json.dumps({"training_started": False, "error": f"export HTTP {exc.code}"}), flush=True)
        except (OSError, RuntimeError, ValueError, subprocess.CalledProcessError) as exc:
            print(json.dumps({"training_started": False, "error": str(exc)}), flush=True)
        if not args.watch:
            return 0
        time.sleep(POLL_SECONDS)


if __name__ == "__main__":
    raise SystemExit(main())
