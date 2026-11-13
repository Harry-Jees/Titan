# Titan Autonomous Internet Exploration — first session

## What it does

The Python engine starts from an optional public URL or discovers a random public Wikipedia article. It extracts article text, follows discovered links breadth-first across public domains, and records an extractive summary, keywords, canonical response URL, fetch time and SHA-256 digest.

The first-session engine is independent of hosted inference. It does **not** claim model-level semantic understanding: summaries and keywords are extractive. Titan's local gpt-oss runtime is not connected yet. This enables a real crawler session without inference charges.

## Run

Requirements: Python 3.11+ and the dependencies in training/requirements.txt.

    python -m pip install -r training/requirements.txt
    python -m titan_explorer --minutes 30 --verbose

Start from a topic page:

    python -m titan_explorer --minutes 30 --seed https://en.wikipedia.org/wiki/Artificial_intelligence --verbose

Seeds are starting points, not a domain allowlist. Stop early with Ctrl+C.

## Output

- titan-exploration/pages.jsonl — source-attributed page records.
- titan-exploration/session.json — duration, counts and stop reason.

The session is capped at 30 minutes and 1,500 successful pages (default 500). It may finish earlier if the frontier is exhausted or the page cap is reached.

## Boundaries

- Public HTTP(S) pages only; rejects private, loopback and link-local IPs.
- Checks robots.txt, fails closed if policy cannot be fetched, and paces requests per host.
- HTML only; maximum 1.5 MB response and 18,000 extracted characters per page.
- No login, credentials, cookies, form submission, scripts, binary downloads or downloaded-code execution.
- Crawled text is untrusted data, never instructions to Titan.
- No production D1 writes, external API actions, model calls or training.

A human reviews the resulting dataset before importing it into Titan's knowledge store.

## Next integration

Connect JSONL output to Titan's source-attributed knowledge ingestion, then add an opt-in local gpt-oss page-understanding adapter. Preserve original URLs and hashes as provenance.
