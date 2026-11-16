"""Sync this cycle's source-attributed chunks to Titan's authenticated D1-backed index."""
import hashlib, json, os, sys, time
from pathlib import Path
import requests
endpoint = os.environ.get("TITAN_KNOWLEDGE_URL", "").rstrip("/")
admin_token = os.environ.get("TITAN_ADMIN_TOKEN", "")
path = Path(sys.argv[1] if len(sys.argv) > 1 else "training/knowledge_chunks_cycle.jsonl")
if not endpoint or not admin_token:
    print("Knowledge sync skipped: set TITAN_KNOWLEDGE_URL and TITAN_ADMIN_TOKEN secrets.")
    raise SystemExit(0)
if not path.exists():
    print(f"Knowledge sync skipped: {path} not found.")
    raise SystemExit(0)
session = requests.Session()
session.headers.update({"Authorization": f"Bearer {admin_token}", "Content-Type": "application/json"})
batch, sent, inserted, failed = [], 0, 0, 0
def flush(items):
    global sent, inserted, failed
    if not items: return
    for attempt in range(5):
        try:
            response = session.post(endpoint, json={"chunks": items}, timeout=45)
            if response.status_code in (200, 201):
                data = response.json(); sent += len(items); inserted += int(data.get("inserted", 0)); return
            if response.status_code < 500 and response.status_code != 429:
                print(f"Knowledge sync rejected batch ({response.status_code}): {response.text[:300]}")
                failed += len(items); return
        except requests.RequestException as exc: print(f"Knowledge sync attempt {attempt + 1} failed: {exc}")
        time.sleep(min(2 ** attempt, 16))
    failed += len(items)
with path.open(encoding="utf-8") as stream:
    for line in stream:
        try: row = json.loads(line)
        except json.JSONDecodeError: continue
        source = str(row.get("source_url") or row.get("url") or "")
        content = str(row.get("content") or row.get("chunk") or row.get("text") or "").strip()[:5000]
        if not source.startswith(("http://", "https://")) or not content: continue
        batch.append({"source_url":source,"title":str(row.get("title") or "")[:300],"content":content,
                      "content_hash":hashlib.sha256((source + "\n" + content).encode()).hexdigest()})
        if len(batch) >= 20: flush(batch); batch = []
if batch: flush(batch)
print(f"Knowledge sync summary: accepted chunks={sent}, newly inserted={inserted}, failed chunks={failed}.")
if failed: raise SystemExit(1)
