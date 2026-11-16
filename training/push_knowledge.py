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
from urllib.parse import urlparse

import requests

ROOT = Path(__file__).resolve().parent
CYCLE = Path(os.getenv("TITAN_CYCLE_OUT", ROOT / "crawled_pages_cycle.jsonl"))
API_BASE = os.getenv("TITAN_API_BASE", "").strip().rstrip("/")
ADMIN_TOKEN = os.getenv("TITAN_ADMIN_TOKEN", "")
CHUNK_LIMIT = int(os.getenv("TITAN_INGEST_CHUNK_LIMIT", "300"))
if not 1 <= CHUNK_LIMIT <= 1000:
    raise ValueError("TITAN_INGEST_CHUNK_LIMIT must be between 1 and 1000.")
CHUNK_CHARS = 800
BATCH_SIZE = 25
MAX_BATCH_BYTES = 17_000
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
    """Select a balanced mix so broad page crawling cannot starve OSINT feeds."""
    osint_chunks: list[dict[str, str]] = []
    general_chunks: list[dict[str, str]] = []
    seen: set[str] = set()
    if not path.exists():
        return []
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
            target = osint_chunks if page.get("source_id") else general_chunks
            for part_number, content in enumerate(split_text(body), 1):
                fingerprint = hashlib.sha256((source + "\n" + content).encode()).hexdigest()
                if fingerprint in seen:
                    continue
                seen.add(fingerprint)
                target.append({
                    "source_url": source,
                    "title": f"{title} (part {part_number})"[:300],
                    "content": content[:5000],
                    "content_hash": fingerprint,
                })

    # Reserve half the per-run ingestion capacity for OSINT records. If one
    # pool is sparse, backfill unused capacity from the other pool.
    osint_quota = min(len(osint_chunks), (CHUNK_LIMIT + 1) // 2)
    general_quota = min(len(general_chunks), CHUNK_LIMIT - osint_quota)
    remaining = CHUNK_LIMIT - osint_quota - general_quota
    extra_osint = min(remaining, len(osint_chunks) - osint_quota)
    osint_quota += extra_osint
    remaining -= extra_osint
    general_quota += min(remaining, len(general_chunks) - general_quota)
    return osint_chunks[:osint_quota] + general_chunks[:general_quota]


def build_batches(chunks: list[dict[str, str]]) -> list[list[dict[str, str]]]:
    """Pack requests below the Worker JSON body limit with a safety margin."""
    batches: list[list[dict[str, str]]] = []
    current: list[dict[str, str]] = []
    for chunk in chunks:
        candidate = current + [chunk]
        size = len(json.dumps({"chunks": candidate}, ensure_ascii=False).encode("utf-8"))
        if current and (len(candidate) > BATCH_SIZE or size > MAX_BATCH_BYTES):
            batches.append(current)
            current = [chunk]
        else:
            current = candidate
        single_size = len(json.dumps({"chunks": current}, ensure_ascii=False).encode("utf-8"))
        if single_size > MAX_BATCH_BYTES:
            raise ValueError("A single knowledge chunk exceeds the safe Worker request size.")
    if current:
        batches.append(current)
    return batches


def post_batch(session: requests.Session, url: str, chunks: list[dict[str, str]]) -> dict:
    payload = {"chunks": chunks}
    for attempt in range(MAX_RETRIES):
        try:
            response = session.post(url, json=payload, timeout=(10, 45))
        except requests.RequestException:
            if attempt + 1 == MAX_RETRIES:
                raise
            time.sleep(min(30, 2 ** attempt))
            continue
        if response.status_code == 429 or response.status_code >= 500:
            retry_after = response.headers.get("Retry-After", "")
            delay = int(retry_after) if retry_after.isdigit() else 2 ** attempt
            status = response.status_code
            response.close()
            if attempt + 1 == MAX_RETRIES:
                raise RuntimeError(f"Titan ingestion failed after retries (HTTP {status}).")
            time.sleep(max(1, min(30, delay)))
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
    parsed = urlparse(API_BASE)
    if parsed.scheme != "https" or not parsed.hostname or parsed.path not in ("", "/"):
        raise SystemExit("TITAN_API_BASE must be an HTTPS origin without a path.")
    if not ADMIN_TOKEN:
        raise SystemExit("TITAN_ADMIN_TOKEN is required.")
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
    batches = build_batches(chunks)
    for batch_number, batch in enumerate(batches, 1):
        result = post_batch(session, endpoint, batch)
        for key in totals:
            totals[key] += int(result.get(key, 0))
        print(f"Indexed batch {batch_number}/{len(batches)}: {result}")
    session.close()
    print(json.dumps({"chunks_submitted": len(chunks), **totals}, sort_keys=True))
    if totals["valid"] != totals["accepted"]:
        print("Warning: Titan rejected one or more source chunks.", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
