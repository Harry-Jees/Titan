#!/usr/bin/env python3
"""Fetch curated public OSINT feeds through Titan's DNS-pinned transport.

Only explicitly registered HTTPS endpoints are requested. Robots policy,
per-host pacing, response-size limits, and source-level budgets are enforced.
The output uses the existing JSONL format consumed by push_knowledge.py.
"""
from __future__ import annotations

import json
import os
import re
import sys
import time
import urllib.robotparser
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
import xml.etree.ElementTree as ET
from pathlib import Path
from urllib.parse import urlparse

import requests

try:
    from .crawler_policy import CrawlerConfig
    from .pinned_http import UnsafeCrawlerURL, mount_pinned_transport, safe_get
except ImportError:
    from crawler_policy import CrawlerConfig
    from pinned_http import UnsafeCrawlerURL, mount_pinned_transport, safe_get

ROOT = Path(__file__).resolve().parent
REGISTRY = Path(os.getenv("TITAN_OSINT_REGISTRY", ROOT / "osint_sources.json"))
OUTPUT = Path(os.getenv("TITAN_CYCLE_OUT", ROOT / "crawled_pages_cycle.jsonl"))
CONFIG = CrawlerConfig.from_env()
MAX_FEED_BYTES = min(CONFIG.max_page_bytes, int(os.getenv("TITAN_OSINT_MAX_FEED_BYTES", "4000000")))
MAX_ITEMS_PER_SOURCE = max(1, min(2000, int(os.getenv("TITAN_OSINT_ITEMS_PER_SOURCE", "500"))))
PER_HOST_DELAY = CONFIG.per_host_delay
USER_AGENT = os.getenv("TITAN_CRAWLER_UA", "TitanOSINTResearchBot/1.0 (+public research; contact via repository)")
SESSION = requests.Session()
mount_pinned_transport(SESSION, config=CONFIG)
SESSION.headers.update({"User-Agent": USER_AGENT, "Accept": "application/atom+xml,application/rss+xml,application/xml,application/json,text/plain,*/*"})
ROBOTS: dict[str, urllib.robotparser.RobotFileParser] = {}
LAST_HIT: dict[str, float] = {}


def request(url: str, headers: dict[str, str] | None = None):
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    wait = PER_HOST_DELAY - (time.monotonic() - LAST_HIT.get(host, 0))
    if wait > 0:
        time.sleep(wait)
    LAST_HIT[host] = time.monotonic()
    response = safe_get(SESSION, url, headers=headers or {}, timeout=CONFIG.fetch_timeout, stream=True, max_redirects=4, same_host_redirects=True)
    if response.status_code != 200:
        status = response.status_code
        response.close()
        return None, status
    length = response.headers.get("content-length")
    if length and length.isdigit() and int(length) > MAX_FEED_BYTES:
        response.close()
        return None, "too-large"
    chunks, total = [], 0
    for chunk in response.iter_content(65536):
        total += len(chunk)
        if total > MAX_FEED_BYTES:
            response.close()
            return None, "too-large"
        chunks.append(chunk)
    response.close()
    return b"".join(chunks), 200


def robots_allowed(url: str) -> bool:
    parsed = urlparse(url)
    origin = f"{parsed.scheme}://{parsed.netloc}"
    if origin not in ROBOTS:
        parser = urllib.robotparser.RobotFileParser()
        parser.set_url(origin + "/robots.txt")
        try:
            body, status = request(origin + "/robots.txt")
            if body and status == 200:
                parser.parse(body.decode("utf-8", "replace").splitlines())
            elif status == 404:
                parser.parse([])
            else:
                parser.parse(["User-agent: *", "Disallow: /"])
        except (requests.RequestException, UnsafeCrawlerURL, OSError, ValueError):
            parser.parse(["User-agent: *", "Disallow: /"])
        ROBOTS[origin] = parser
    return ROBOTS[origin].can_fetch(USER_AGENT, url)


def value_at(record, path: str):
    value = record
    for part in path.split(".") if path else []:
        if isinstance(value, list):
            try:
                value = value[int(part)]
            except (ValueError, IndexError):
                return None
        elif isinstance(value, dict):
            value = value.get(part)
        else:
            return None
    return value


def text_value(value) -> str:
    if value is None:
        return ""
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False)
    return re.sub(r"\s+", " ", str(value)).strip()


def json_records(source: dict, payload):
    records = value_at(payload, source.get("records_path", ""))
    if records is None and isinstance(payload, list):
        records = payload
    if not isinstance(records, list):
        records = [records] if isinstance(records, dict) else []
    for record in records[:MAX_ITEMS_PER_SOURCE]:
        title = text_value(value_at(record, source.get("title_path", ""))) or source["name"]
        lines = [f"Source: {source['name']}", f"Category: {source['category']}"]
        for path in source.get("summary_paths", []):
            value = text_value(value_at(record, path))
            if value:
                lines.append(f"{path}: {value}")
        link = text_value(value_at(record, source["url_path"])) if source.get("url_path") else ""
        if link.startswith("https://") or link.startswith("http://"):
            source_url = link
        else:
            source_url = source["url"]
            if link:
                lines.append(f"Reference: {link}")
        published = text_value(value_at(record, source.get("date_path", "")))
        yield {"title": title[:450], "text": "\n".join(lines), "url": source_url, "published": published}


def xml_records(source: dict, body: bytes):
    root = ET.fromstring(body)
    items = [node for node in root.iter() if node.tag.rsplit("}", 1)[-1].lower() in {"item", "entry"}]
    for item in items[:MAX_ITEMS_PER_SOURCE]:
        fields = {}
        for child in item.iter():
            key = child.tag.rsplit("}", 1)[-1].lower()
            if child.text and child.text.strip() and key not in fields:
                fields[key] = re.sub(r"\s+", " ", child.text).strip()
            if key == "link" and child.attrib.get("href"):
                fields.setdefault("link", child.attrib["href"])
        title = fields.get("title", source["name"])
        link = fields.get("link", source["url"])
        published = fields.get("pubdate") or fields.get("published") or fields.get("updated") or ""
        summary = fields.get("description") or fields.get("summary") or fields.get("content") or ""
        text = "\n".join([
            f"Source: {source['name']}", f"Category: {source['category']}",
            f"Title: {title}", f"Published: {published}", f"Summary: {summary[:5000]}",
        ])
        yield {"title": title[:450], "text": text, "url": link if link.startswith(("https://", "http://")) else source["url"], "published": published}


def text_records(source: dict, body: bytes):
    lines = [line.strip() for line in body.decode("utf-8", "replace").splitlines() if line.strip() and not line.lstrip().startswith("#")]
    for line in lines[:MAX_ITEMS_PER_SOURCE]:
        yield {
            "title": f"{source['name']} indicator",
            "text": f"Source: {source['name']}\nCategory: {source['category']}\nPublic feed record: {line[:1500]}",
            "url": source["url"],
            "published": "",
        }


def main() -> int:
    if not REGISTRY.exists():
        raise SystemExit(f"OSINT registry missing: {REGISTRY}")
    registry = json.loads(REGISTRY.read_text(encoding="utf-8"))
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    seen = set()
    if OUTPUT.exists():
        with OUTPUT.open("r", encoding="utf-8") as handle:
            for line in handle:
                try:
                    item = json.loads(line)
                    seen.add((item.get("url"), item.get("title"), item.get("text", "")[:250]))
                except json.JSONDecodeError:
                    continue
    totals = {"sources": 0, "records": 0, "skipped": 0, "blocked": 0, "errors": 0}
    with OUTPUT.open("a", encoding="utf-8") as output:
        for source in registry.get("sources", []):
            url = source.get("url", "")
            if not url.startswith("https://") or not source.get("id") or not source.get("category"):
                totals["skipped"] += 1
                continue
            try:
                headers = {}
                request_url = url
                header_env = source.get("auth_header_env")
                if header_env:
                    token = os.getenv(header_env, "").strip()
                    if not token:
                        print(f"Skipped optional source (missing {header_env} secret): {source['id']}")
                        totals["skipped"] += 1
                        continue
                    headers[source.get("auth_header", "Authorization")] = token
                query_env = source.get("auth_query_env")
                if query_env:
                    token = os.getenv(query_env, "").strip()
                    if not token:
                        print(f"Skipped optional source (missing {query_env} secret): {source['id']}")
                        totals["skipped"] += 1
                        continue
                    parsed = urlsplit(request_url)
                    params = dict(parse_qsl(parsed.query, keep_blank_values=True))
                    params[source.get("auth_query_name", "key")] = token
                    request_url = urlunsplit((parsed.scheme, parsed.netloc, parsed.path, urlencode(params), parsed.fragment))
                if not robots_allowed(url):
                    print(f"Skipped disallowed source: {source['id']}")
                    totals["skipped"] += 1
                    continue
                body, status = request(request_url, headers=headers)
                if not body or status != 200:
                    print(f"Source unavailable or over budget: {source['id']} ({status})")
                    totals["skipped"] += 1
                    continue
                kind = source.get("kind")
                if kind == "json":
                    payload = json.loads(body.decode("utf-8", "replace"))
                    records = json_records(source, payload)
                elif kind == "xml":
                    records = xml_records(source, body)
                elif kind == "text":
                    records = text_records(source, body)
                else:
                    totals["skipped"] += 1
                    continue
                source_count = 0
                for record in records:
                    text = record["text"].strip()
                    if len(text) < 40:
                        continue
                    key = (record["url"], record["title"], text[:250])
                    if key in seen:
                        continue
                    seen.add(key)
                    item = {
                        "url": record["url"],
                        "source_url": url,
                        "title": record["title"],
                        "text": text[:12000],
                        "category": source["category"],
                        "source_id": source["id"],
                        "published": record.get("published", ""),
                    }
                    output.write(json.dumps(item, ensure_ascii=False) + "\n")
                    source_count += 1
                    totals["records"] += 1
                output.flush()
                totals["sources"] += 1
                print(f"Collected {source['id']}: {source_count} new records")
            except UnsafeCrawlerURL:
                # A rejected redirect or DNS answer is an expected policy block,
                # not a reason to discard the successful records from other feeds.
                totals["blocked"] += 1
                print(f"Source blocked by crawler safety policy: {source.get('id', 'unknown')}", file=sys.stderr)
            except (requests.RequestException, ET.ParseError, json.JSONDecodeError, OSError, ValueError, KeyError) as exc:
                totals["errors"] += 1
                print(f"Source failed {source.get('id', 'unknown')}: {type(exc).__name__}", file=sys.stderr)
    SESSION.close()
    print(json.dumps(totals, sort_keys=True))
    # A transient source failure is visible to the workflow, but successful
    # sources remain on disk for indexing. The workflow isolates this step.
    return 0 if totals["errors"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
