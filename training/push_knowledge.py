#!/usr/bin/env python3
"""Upload a bounded crawler cycle to Titan's authenticated knowledge API."""
from __future__ import annotations

import hashlib
import json
import os
import sys
import time
from pathlib import Path
from typing import Iterator

import requests

ROOT = Path(__file__).resolve().parent
CYCLE = Path(os.getenv("TITAN_CYCLE_OUT", ROOT / "crawled_pages_cycle.jsonl"))
API_BASE = os.getenv("TITAN_API_BASE", "").strip().rstrip("/")
ADMIN_TOKEN = os.getenv("TITAN_ADMIN_TOKEN", "")
CHUNK_LIMIT = int(os.getenv("TITAN_INGEST_CHUNK_LIMIT", "300"))
CHUNK_CHARS = 4200
BATCH_SIZE = 25
MAX_RETRIES = 4


def split_text(value: str, limit: int = CHUNK_CHARS) -> Iterator[str]:
    """Split extracted text into bounded paragraph-aware chunks."""
    paragraphs = [part.strip() for part in value.splitlines() if part.strip()]
    current = ""
    for paragraph in paragraphs:
        while len(paragraph) > limit:
            if current:
                yield current
                current = ""
            yield paragraph[:limit]
            paragraph = paragraph[limit:]
        candidate = f"{current}\n\n{paragraph}".strip() if current else paragraph
        if len(candidate) > limit:
            if current:
                yield current
            current = paragraph
        else:
            current = candidate
    if current:
        yield current


def read_chunks(path: Path) -> list[dict[str, str]]:
    output: list[dict[str, str]] = []
    seen: set[str] = set()
    if not path.exists():
        return output
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, 1):
            if not line.strip():
                continue
            try:
                page = json.loads(line)
            except json.JSONDecodeError as exc:
                print(f"Skipping malformed JSONL line {line_number}: {exc}", file=sys.stderr)
                continue
            source = str(page.get("url") or page.get("source_url") or "").strip()
            title = str(page.get("title") or "Untitled source").strip()[:280]
            body = str(page.get("text") or "").strip()
            if not source.startswith("https://") or len(body) < 250:
                continue
            for part_number, content in enumerate(split_text(body), 1):
                fingerprint = hashlib.sha256((source + "\n" + content).encode()).hexdigest()
                if fingerprint in seen:
                    continue
                seen.add(fingerprint)
                output.append({
                    "source_url": source,
                    "title": f"{title} (part {part_number})"[:300],
                    "content": content[:5000],
                    "content_hash": fingerprint,
                })
                if len(output) >= CHUNK_LIMIT:
                    return output
    return output


def post_batch(session: requests.Session, url: str, chunks: list[dict[str, str]]) -> dict:
    payload = {"chunks": chunks}
    for attempt in range(MAX_RETRIES):
        response = session.post(url, json=payload, timeout=(10, 45))
        if response.status_code == 429 or response.status_code >= 500:
            delay = min(30, int(response.headers.get("Retry-After", 2 ** attempt)))
            response.close()
            if attempt + 1 == MAX_RETRIES:
                raise RuntimeError(f"Titan ingestion failed after retries (HTTP {response.status_code}).")
            time.sleep(max(1, delay))
            continue
        if not response.ok:
            detail = response.text[:500]
            response.raise_for_status()
            raise RuntimeError(f"Titan ingestion rejected the batch: {detail}")
        result = response.json()
        response.close()
        return result
    raise RuntimeError("Titan ingestion retry budget exhausted.")


def main() -> int:
    if not API_BASE or not ADMIN_TOKEN:
        raise SystemExit("TITAN_API_BASE and TITAN_ADMIN_TOKEN are required.")
    if not CYCLE.exists():
        print("No crawler cycle file; nothing to index.")
        return 0
    chunks = read_chunks(CYCLE)
    if not chunks:
        print("No new valid public-source chunks to index.")
        return 0

    session = requests.Session()
    session.trust_env = False
    session.headers.update({
        "Authorization": f"Bearer {ADMIN_TOKEN}",
        "Content-Type": "application/json",
        "User-Agent": "TitanResearchIndexer/1.0",
    })
    endpoint = f"{API_BASE}/knowledge"
    totals = {"accepted": 0, "valid": 0, "inserted": 0}
    for offset in range(0, len(chunks), BATCH_SIZE):
        result = post_batch(session, endpoint, chunks[offset:offset + BATCH_SIZE])
        for key in totals:
            totals[key] += int(result.get(key, 0))
        print(f"Indexed batch {offset // BATCH_SIZE + 1}: {result}")
    session.close()
    print(json.dumps({"chunks_submitted": len(chunks), **totals}, sort_keys=True))
    if totals["valid"] != totals["accepted"]:
        print("Warning: Titan rejected one or more source chunks.", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
